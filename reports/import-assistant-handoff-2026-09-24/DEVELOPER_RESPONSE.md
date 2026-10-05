# Developer response: flexible import assistant

> **Released September 24, 2026** (deployment `dpl_3VdC4NrQYuuf6tNBJLYdUFTnBGnV`, schema 6, AI disabled). See [RELEASE_RESPONSE.md](RELEASE_RESPONSE.md).

Response to [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md), September 24, 2026. **Revised after [SUPERVISOR_REVIEW.md](SUPERVISOR_REVIEW.md)** (R1–R5, §0), **[SUPERVISOR_REVIEW_02.md](SUPERVISOR_REVIEW_02.md)** (R2a, R2b, §0b) **and [SUPERVISOR_REVIEW_03.md](SUPERVISOR_REVIEW_03.md)** (disposable-Postgres acceptance, §0c and [ACEPTACION_POSTGRES.md](ACEPTACION_POSTGRES.md)). Prepared for review; **nothing has been deployed, no migration has been run against Neon, and no paid API has been called.**

Final source for this revision: [FINAL_SOURCE_SNAPSHOT.json](FINAL_SOURCE_SNAPSHOT.json) (SHA-256 of every source, test and fixture file, regenerated after the second-review corrections). Before each round of corrections, the code on disk was confirmed identical to the snapshot the supervisor had reviewed.

## 0. Corrections after the supervisor review

The reviewer's [review_regressions.py](review_regressions.py) is unmodified: before the fixes, 6 of its cases failed and 1 errored, as reported. **After: 8/8 pass.** The same cases, plus stronger controls, now run in normal verification as `tests/test_revision_supervisor.py` (26 cases).

| Finding | Correction | Controls added |
|---|---|---|
| **R1** — saved format could swap same-named columns | `detectar._aplicar_formato` still reuses uniquely named columns by name, but withholds columns that share a name when the format gave them different meanings. A single focused question asks which is which, with each column's samples and **nothing preselected**; the rest of the file still comes from the format. Groups the format kept only as extra data need no question. Blank headings are never taken from a format. | Reviewer case; answer "al revés" / "como la vez anterior" produce the named values; "keep both" → no price; 3 same-named columns asked one by one; blank-heading reorder; browser check (`e2e`: reconfirm by keyboard). The unique-header reorder case still reuses silently. |
| **R2** — confirm and correction could both succeed | Confirmation now **claims the draft** with one compare-and-set on its revision (`Borradores.reclamar`) right after taking the single-use token and **before** backup or any write. A correction that got there first makes the claim fail (409, nothing written). A claim that got there first makes every later `preparar` fail (409). Same policy for new-base and append. The claim is a single `UPDATE … WHERE revision = ? RETURNING` in Postgres, under the workspace lock. A failed commit closes the draft, so it can't stay stuck as "saving". | Reviewer case (hook at the backup boundary); an older preview confirmed after a correction writes nothing; **25 real threaded races each** for new-base and append (confirm and correction started together): they never both succeed, and in the new-base races one of the two always does. |
| **R3** — foreign prices relabelled as MXN | `campos.moneda` recognizes explicit markers — `US$`, `USD`, `U$S`, dólares, `EUR`/`€`/euros, `CAD`, `GBP`/`£`, `JPY`/`¥`, `CHF`, `CNY`, `BRL`, `COP`, `ARS`, `CLP` — using lookaround boundaries, so a trailing `$` matches. It scans the header and **every** text cell of the column, not only samples. Enforced for detection, saved formats, automatic suggestions and the user's own choice: the plan refuses a foreign-currency column as a price, and the column stays additional data. A bare `$`, `MXN` and "pesos" remain pesos, and a text column that merely mentions a currency is not affected. No conversion was added. | Reviewer cases; 8 foreign markers × detection and explicit choice; a single `USD` cell after 20 plain ones; 5 peso/unspecified headers still import; address mentioning USD unaffected; saved format and suggestion paths. |
| **R4** — spend cap on an estimate; missing usage = $0 | `ia.costo_maximo` is an **upper bound**, not an estimate. Input tokens ≤ UTF-8 bytes of everything sent (system, user content **and the response schema**; byte-level BPE encodes ≥1 byte per token), plus 512 tokens of framing. Output ≤ the enforced `max_completion_tokens`, which for reasoning models includes reasoning tokens. A request whose bound doesn't fit the remaining budget is **refused before calling**. Settlement records actual usage only when it is trustworthy (non-negative integers). Missing, negative or non-integer usage keeps the **full reservation** as the charge (`ok_uso_desconocido`). Usage above the bound is recorded whole and flagged `…_sobre_reserva`, never clipped. Refusals record their reported usage. Only HTTP 429 (certainly not processed) releases a reservation. Timeouts, 5xx and unreadable responses keep it. | Reviewer case (now refused before calling, 0 provider calls); worst-case usage within the bound fits the reservation; overrun recorded and flagged; 5 missing/invalid usage shapes; per-failure charge table; 4 simultaneous callers with one call in flight → exactly one call; spending read back from a fresh connection after "restart" and the next call refused. |
| **R5** — malformed AI value aborted analysis | `ia.validar` checks every type before any lookup, so malformed data is always `invalido`. `ia.sugerir` also turns any unexpected provider or validation exception into a fallback, logging only the exception **type**, never its message or the file content. | Reviewer case through `api.analizar`; 13 malformed shapes (arrays/objects/null/numbers in IDs and fields, wrong envelope types) all fall back to questions; a provider raising an exception whose message contains terrain data → fallback, and the log contains only `ValueError`. |

My own background code review did not return a result before this revision. The supervisor's reviews are the reviews addressed here.

## 0b. Corrections after the second supervisor review

The reviewer's [review2_regressions.py](review2_regressions.py) is unmodified: before the fixes, all 4 cases failed, as reported. **After: 4/4 pass**, and the first review's 8 cases still pass. The four cases, plus stronger controls, run in normal verification as `tests/test_revision_supervisor_2.py` (17 cases).

| Finding | Correction | Controls added |
|---|---|---|
| **R2a** — a missing draft let a stale confirmation write | For a preview that carries assistant draft metadata, `_vigente` now requires a **successful claim of a present, unexpired draft at the exact revision**. `reclamar` returning False (draft deleted after another revision was imported, expired, or evicted) is answered with **410** before any write. It is never treated as permission. Expiry is checked inside the claim in both stores: `AND creado >= ?` in Postgres, a purge before the check locally. Legacy previews without assistant metadata keep their separate early return. The atomic ownership rule is unchanged. | Reviewer's three-request ordering for new base **and** append: the corrected import succeeds, the old request gets 409/410, one base remains, and the price stays unknown. Missing, expired and evicted drafts all return 410 with nothing written. Replaying an already-claimed preview returns 409. A legacy `/vista-previa` preview still confirms. |
| **R2b** — cleanup reacquired the cloud lock | A small context manager, `_confirmacion`, now owns the lifecycle from the claim to the end. The draft is closed **after the business-data session has exited**, on success and on failure, so cleanup's own session never waits on a lock its caller holds. Errors keep their type and message. A cleanup failure is logged by type only and never replaces the import's real outcome; if deletion fails, the draft stays claimed, so no stale request can use it. Input that can be checked earlier (name, conflict choices) is now validated **before** the single-use token is spent. An `ApiError` raised after the claim is marked `vista_previa_consumida`. The dialog then states plainly that nothing was imported and the file must be reselected, and stops offering "Importar". | Reviewer's session-depth cases for new base and append (cleanup at depth 0). Successful commits also clean up at depth 0. A provenance/format write failure rolls back base, terrains, format and import record together. A backup failure after the claim closes the draft. The spent preview then answers 410 to both confirm and prepare. A destination folder deleted after validation, and an append base deleted before commit, both give 404 marked spent, with the draft closed. Cleanup failure: success stays success, and the original error stays the original error. A bad name or bad conflict choices return 400 without spending the preview. JS: `vistaConsumida` rules. |

The same two orderings are written for **disposable Postgres** in `tests/test_postgres.py`: the late confirmation after a corrected import, and a failed commit whose cleanup must finish promptly with no rows, formats or records left. They use separate connections per request. They are **not run** here, because no test database is available.

## 0c. Disposable-Postgres acceptance (third review)

Run against a throwaway local PostgreSQL 17.11, bound to 127.0.0.1 only; production Neon untouched. The full packet is in [ACEPTACION_POSTGRES.md](ACEPTACION_POSTGRES.md). In short:

- All **10 existing Postgres cases execute and pass**, plus **10 new acceptance cases** in `tests/test_postgres_aceptacion.py`: append late-confirmation and failure cleanup, threaded confirm-vs-correct on separate connections, injected failures with no residue followed by a working import, cross-connection budget reservations with the in-process lock removed, migration from a v5 workspace **using the real migration script**, and a cloud merge regression.
- The **entire suite with the disposable database configured: 545 run, 0 skipped, all pass.** The Postgres suites passed 5 consecutive times.
- The **browser suite through the app with Postgres as storage passes 44/44**, both without AI and with the simulated provider.
- **Defect found and fixed (pre-existing; expected in the currently deployed web version, not inspected there):** merging saved maps in the cloud could discard distinct layers with equal terrain counts as duplicates. Details in the packet.
- `scripts/migrate_cloud.py` gained `--url-env NAME`, so a test database can be upgraded without ever reading `.env.local`. A missing variable is a refusal, not a fall-back to production.

## 1. Status at a glance

| Part | Status |
|---|---|
| **Milestone 1** — discovery, deterministic detection, targeted questions, optional corrections, reusable formats, preview/commit, SQLite + Postgres schema | **Implemented and tested locally; supervisor findings R1–R3 corrected.** Postgres paths are unit-tested with mocks and have disposable-schema tests written, but **not run** (no test database available). |
| **Supervisor findings R1–R5** | **Corrected**, with regressions in normal verification (§0). |
| **Second review R2a, R2b** | **Corrected**, with regressions in normal verification (§0b). |
| **Milestone 2** — automatic AI assistance | **Implemented and tested against stubs only.** OpenAI adapter, budget cap, rate limit, validation and fallback all tested with a fake transport. |
| **Real-provider verification** | **Not done.** Needs the administrator setup in §9. Until then the assistant runs on detection + questions, which is the complete no-key path the brief requires. |
| Three demonstration journeys | Demonstrated in unit, API and browser tests; screenshots in [`capturas/`](capturas/). |

The manager never sees an AI toggle, a model or a provider setting. With assistance unconfigured, the flow is identical except that a file which would have needed it asks focused questions instead.

## 2. What the manager experiences

`Bases → Importar archivo` (or `Agregar terrenos` on a base) opens one dialog:

1. **Analizando archivo…** — table, header row, columns and number convention are detected automatically. If detection leaves a needed field unresolved and assistance is configured, it is called here, once.
2. **Preguntas** — only what is genuinely unclear, with the file's own column names and sample values. A clear file skips this step entirely.
3. **Vista previa** — terrain/map/price counts, a small map of located points, the first 100 rows with their original values (`Ver`), rejected and excluded rows with reasons, data findings, append conflicts. Name, folder and **Recordar este formato** (on by default).
4. **Importar / Agregar** — the existing confirmation and append endpoints commit exactly the previewed result.

Optional, collapsed by default: **Corregir interpretación** (table, header row, number convention, and each column's destination including *Conservar como dato adicional* and *No importar*) and **Detalles de la detección** (why each column was read as it was, the convention used, the saved format applied, and how automatic assistance went). **Formatos de importación** in the Bases header renames or forgets remembered formats.

| Screenshot | Shows |
|---|---|
| [1-conocido-vista-previa](capturas/1-conocido-vista-previa.png), [1b](capturas/1b-conocido-filas.png) | Familiar file: straight to preview, map, rows |
| [2a-desconocido-titulos-y-totales](capturas/2a-desconocido-titulos-y-totales.png) | Unfamiliar layout (title rows, hectares, totals row) read without questions |
| [2b-desconocido-asistencia-simulada](capturas/2b-desconocido-asistencia-simulada.png) | Unrecognized headers resolved by (simulated) automatic assistance, with provenance |
| [3a-ambiguo-pregunta](capturas/3a-ambiguo-pregunta.png), [3b](capturas/3b-ambiguo-vista-previa.png) | Ambiguous «Valor» column: one question, then preview |
| [4-corregir-interpretacion](capturas/4-corregir-interpretacion.png) | Optional correction editor |
| [5-formatos](capturas/5-formatos.png) | Remembered format after import |
| [6-movil-pregunta-coordenadas](capturas/6-movil-pregunta-coordenadas.png) | 375 px: X/Y values contradict ARA's convention → question |

## 3. The three required journeys

| Journey | Fixture | Result |
|---|---|---|
| Familiar file | `familiar_reordenado.csv` (ARA headers, reordered) and the real `base_terrenos_09_26.xlsx` | Upload → preview → import. No question, no AI call. The ARA workbook produces records **identical** to the legacy importer (`tests/test_asistente.py::Equivalencia`), and downstream base/map/comparison results match (`test_asistente_api.py::test_assistant_base_equals_legacy_base_downstream`). |
| Unfamiliar, interpreted automatically | `desconocido_titulos.xlsx` (deterministic) and `desconocido_ia.csv` (needs assistance) | The first is read without questions: title rows skipped, second sheet ignored, totals row excluded, hectares kept as hectares. The second is resolved by the (stubbed) assistant and validated against the file's values. **With assistance unavailable it falls back to focused questions and still reaches a preview.** |
| Ambiguous, one clarification | `ambiguo_valor.csv` | Exactly one question — «¿Qué representa la columna «Valor»?» with sample values — then preview. An AI suggestion may preselect an answer but never settles it. |

## 4. Architecture and contracts

### Server (`server/asistente/`)

| Module | Responsibility |
|---|---|
| `rejilla.py` | Structure only: CSV (strict quoting, UTF-8/BOM, `sep=`, comma/semicolon chosen by table shape, never by field names) and Excel (typed cells, cached formula results only, formulas never run, missing cached results reported). Bounded: 50,000 rows, 200 columns, 30 sheets, 5,000 chars/cell, 300 MB decompressed. Lossless, compressed packing for drafts. |
| `campos.py` | Target fields, legacy aliases + curated synonyms, and `respaldo()` — the evidence gate every non-user assignment passes (text vs number, money words, per-m² vs total, m² vs ha, Mexican lat/lon ranges, USD). |
| `perfil.py` | Positional column IDs (`sheet:0/column:4`, `csv:;/column:2`), unique display names for duplicate/blank headings, type summaries, ≤5 samples. |
| `detectar.py` | Chooses table and header (search bounded to 50 rows; any row selectable), applies trust order *default → saved format → name/alias → values → automatic → user*, and emits questions. |
| `plan.py` | Versioned `ImportPlan`, server validation, and record building through the existing `_build_record`. |
| `ia.py` | Automatic assistance (§6). |
| `borradores.py` | Drafts: memory locally; Postgres table `borrador_importacion` in the cloud; 60-min expiry, bounded count, compare-and-set on revision. |
| `servicio.py` | Orchestration for the endpoints. |

### `ImportPlan` (version 1)

```json
{ "version": 1, "parser": 1, "sha256": "<file hash>",
  "hoja_id": "sheet:0 | csv:, | csv:;", "encabezado": 2,
  "decimal": "dot | comma",
  "asignaciones": { "sheet:0/column:0": "terreno", "sheet:0/column:7": "extra", "…": "ignorar" },
  "excluir": [5],
  "origenes": { "sheet:0/column:0": "alias", "…": "usuario | formato | nombre | valores | ia | predeterminado" } }
```

Validated on the server: file hash and parser version, sheet exists, header in range, every column ID real, every destination allowlisted, **at most one column per field**, name present, no USD column as a price, exclusions only in the data region. The client never sends terrain records — only answers and corrections.

### Endpoints

| Request | Body | Returns |
|---|---|---|
| `POST /api/importar/analizar[?base_id=]` | raw bytes + `X-Archivo` (same limits: 25 MB local / 4 MB cloud) | `{borrador, revision, estado: "preguntas" \| "vista_previa" \| "revisar", preguntas?, vista_previa?, interpretacion, error?}` |
| `POST /api/importar/preparar` | `{borrador, revision, respuestas: [{pregunta, opcion}], correcciones: {hoja?, encabezado?, decimal?, columnas?, excluir?}}` | same shape, new revision; **409** on a stale revision, **410** on an expired draft |
| `POST /api/importar/confirmar`, `POST /api/bases/:id/adjuntar` | existing, plus optional `recordar_formato` (default true) | existing; `formato: {id, version, accion}` when a format was remembered |
| `GET /api/formatos`, `PATCH`/`DELETE /api/formatos/:id` | — / `{nombre}` | formats (no cell values) |

Questions carry option **indices**; the server applies the option's decision itself, so the client cannot inject arbitrary decisions. The legacy `POST /api/importar/vista-previa` is kept for compatibility.

**Revisions and tokens.** Every answer or correction creates a new draft revision and a new preview token; the previous preview token is deleted, and confirmation additionally checks that the preview's revision is still the draft's latest (409 otherwise). Tokens remain single-use. In the dialog, corrections are queued and coalesced, so the newest choice always wins and saving is disabled while a preview is missing or rebuilding.

**Access.** In the cloud, `/api/importar/*` and `/api/formatos*` require an editor session **including GETs** (`api/index.py`). Locally, read-only mode (`ARA_MAP_READ_ONLY=1`) refuses all writes with 403.

## 5. Safeguards (brief §4–§5)

- **Coordinates:** ARA's X = latitude / Y = longitude stays the visible default. If X/Y values contradict it, a question shows both samples; nothing is swapped silently. Norte/Este are used only when their values are geographic; projected values (UTM) stay additional data with an explanation. Range checks read both number conventions, so `20,653` counts as a latitude before the convention is settled.
- **Numbers:** one explicit convention per plan. It is detected only when values establish it (e.g. a coordinate impossible under one reading); otherwise the question shows both readings («¿«1,250» significa 1250 o 1.25?»). Typed Excel numbers never change with the convention. The legacy Excel converter is untouched.
- **Units and money:** total price vs price/m², m² vs ha, and percent vs m² are separate fields. Nothing is converted or computed. A missing price stays unknown. A column explicitly in another currency (header or any cell; see §0, R3) cannot become a price by any path — detection, saved format, suggestion or the user — and is kept as additional data.
- **Saved formats and repeated headings:** uniquely named columns are matched by name in any order. Columns that share a name and were given different meanings are reconfirmed with one question (§0, R1).
- **Accounting:** every nonblank row below the header is accepted, rejected (with reason) or excluded (totals, repeated header, or the user's choice). Rows above the header are listed as titles. Source row/line numbers are preserved.
- **Structure:** duplicate/blank headings stay separate by position; CSV data rows must match the header width (error names the line); malformed quoting, unsupported encodings, Excel-renamed-as-CSV and oversized workbooks remain readable errors.

## 6. Automatic assistance (milestone 2)

- **When:** only if detection leaves the name unresolved, or leaves unrecognized numeric columns while a key field (price, area, coordinates) is missing, and no saved format matched. Familiar files never call it. At most **one attempt per table choice and two per draft**. The attempt is claimed on the draft before calling out, so concurrent requests don't duplicate it; answers, corrections, retries and returning to the preview never trigger new calls.
- **What is sent:** headers; a type/range summary and at most 3 samples of ≤40 characters **for unresolved columns only**. Resolved columns send their header and assigned field. Columns that look like contact data or notes send no samples. Never the file or full rows. `ARA_MAP_IA_MUESTRAS=0` sends headers and summaries only.
- **What comes back:** a strict JSON schema (OpenAI Structured Outputs) whose enums are the allowed column IDs and fields, plus `desconocido`. It is validated structurally (`ia.validar`) **and** semantically (`detectar._aplicar_ia` via `campos.respaldo`). It never overrides names, saved formats or the user, never resolves a price/unit/coordinate ambiguity (it can only preselect an answer), and an unsupported suggestion becomes a question.
- **Prompt injection:** cell text is labelled as data in the system prompt; the model has no tools; any output that doesn't fit the file's evidence is discarded. Tested with a cell reading «Ignora tus reglas…».
- **Cost control:** an upper bound on the request's cost (§0, R4) is reserved in `uso_ia` before calling (monthly cap, persisted, serialized). The request is refused if the bound doesn't fit. Afterwards the actual cost is recorded only when the reported usage is trustworthy; otherwise the reservation stands. There's a per-hour call limit and a timeout. Usage rows hold counts, costs and latency only, and logs hold only the failure state or exception type, never headers, samples or messages.
- **Confirmation vs corrections:** confirming claims the draft atomically before writing, so a newer correction and an older confirmation can never both succeed (§0, R2).
- **Failure:** missing configuration, budget reached, rate limit, timeout, HTTP error, refusal or malformed output all fall back silently to detection + questions. The manager is never asked to fix configuration.
- **Outside DB locks:** the external call runs outside any database session.

## 7. Storage, migrations and backups

**Schema v6** (additive; SQLite upgrades automatically with the existing pre-upgrade backup):

| Table | Purpose | In workspace backups |
|---|---|---|
| `formato_importacion` | Header signature, per-header decisions, convention, version; `reemplazado_por` marks superseded versions. **No cell values.** | yes |
| `importacion` | Per-import provenance: file name/hash, sheet, header row, full plan, format used. Appends add rows; they never rewrite the original. | yes |
| `uso_ia` | Spend/usage ledger for the cap | no |
| `borrador_importacion` (Postgres only) | Temporary drafts | no |

**Cloud (Neon), before deploying this code:**

```bash
.venv-dev/bin/python scripts/migrate_cloud.py --check   # reports the recorded version
.venv-dev/bin/python scripts/migrate_cloud.py           # backup, then idempotent upgrade to v6
```

The upgrade creates the folder and assistant tables in dependency order, adds folder columns and indexes with `IF NOT EXISTS`, and records `schema_version = 6`. It runs under the workspace advisory lock and can be re-run safely. Deploying before migrating would break requests that touch the new tables. Recommended order: disposable/preview database first, then back up production, migrate, deploy, smoke-test with removable fictional data.

## 8. Test results (actual, this environment)

| Suite | Result |
|---|---|
| Python unit/integration (`python3 -m unittest discover -s tests -t .`), default environment | **545 tests run, 20 skipped → 525 executed, all passed.** The 20 skipped are the Postgres cases, which run in the rows below. Assistant tests: `test_asistente.py` 39, `test_asistente_api.py` 24, `test_asistente_ia.py` 16, `test_asistente_migracion.py` 4, `test_revision_supervisor.py` 26, `test_revision_supervisor_2.py` 17. |
| Supervisor's `review_regressions.py`, unmodified | **8/8 pass** (was 1 pass, 6 fail, 1 error) |
| Supervisor's `review2_regressions.py`, unmodified | **4/4 pass** (was 4 fail) |
| Same suite on macOS system Python 3.9.6 | OK |
| JavaScript (`node --test tests/js/*.test.mjs`) | **62 OK** (6 new: answers, queue coalescing, labels, spent-preview rules) |
| ruff / mypy (`./verificar.sh --todo`) | clean / no issues in 38 files |
| Coverage | 93% |
| Browser (`tests/e2e`, Chrome, disposable DB, port 8471) | **44/44** without assistance configured **and 44/44** with the simulated provider, no console errors, re-run on the final code after the second-review corrections. Checks cover all three journeys, remembered format reused, keyboard answering, number-format correction, append with line numbers, no AI choice ever shown, and (new, R1) same-named columns reconfirmed after a swap. |
| Real Postgres (`tests/test_postgres.py` 10 + `tests/test_postgres_aceptacion.py` 10) | **20/20 pass** on disposable PostgreSQL 17.11, 5 consecutive runs; every test schema dropped afterwards. Without `ARA_MAP_TEST_DATABASE_URL` they skip, which is why the default run shows 20 skipped. |
| Entire suite with the disposable DB configured | **545 run, 0 skipped, all pass** |
| Browser suite, app on Postgres storage | **44/44** without AI and **44/44** with the simulated provider |
| Real AI provider | **Not run** — no credentials. |

Fixtures are fictional and generated by [`tests/fixtures/asistente/generar.py`](../../tests/fixtures/asistente/generar.py); the expected outcome of each is asserted in `tests/test_asistente.py`.

### Mapping accuracy on the held-out set

`python3 scripts/evaluar_asistente.py`, 6 files and 37 columns not used while writing the rules:

| Mode | Correct | Left as additional data | **Wrong field** | Questions |
|---|---|---|---|---|
| Deterministic (no assistance) | 31 / 37 (84%) | 6 | **0** | 3 |
| Simulated provider | 35 / 37 (95%) | 2 | **0** | 1 |

The **simulated provider is a header keyword table, not a model**. Its row shows the pipeline and validation working, not what a real model would score. The misses are English headers (`Name`, `Area (m2)`) and abbreviations (`Edo`, `Mpio`, `Sup m2`). All were left visible as additional data or asked about; none was assigned to the wrong field. Request cost and latency for a real model **have not been measured**.

## 9. Administrator setup still required

Automatic assistance stays off until all of these are set as server secrets. `python3 scripts/estado_ia.py` names whatever is missing.

1. `ARA_MAP_IA_PROVEEDOR=openai` — the adapter provided (Chat Completions + Structured Outputs over HTTPS, no new dependency).
2. `ARA_MAP_IA_MODELO` — **to be chosen by a small evaluation** of representative real layouts, latency and measured cost (brief §8). No model is assumed.
3. `ARA_MAP_IA_CLAVE` (or `OPENAI_API_KEY`).
4. `ARA_MAP_IA_LIMITE_MENSUAL_USD` — the agreed monthly budget (must be > 0).
5. `ARA_MAP_IA_COSTO_ENTRADA_USD_MTOK` and `ARA_MAP_IA_COSTO_SALIDA_USD_MTOK` — the chosen model's prices.
6. Before enabling in production: review OpenAI's current API data-controls/retention terms and confirm the permitted data categories. Defaults: headers, summaries, up to 3 short samples of unresolved columns; contact/notes columns withheld.
7. Then run a real-provider check against fictional files and record accuracy, latency and cost.

Optional: `ARA_MAP_IA_TIEMPO_S` (20), `ARA_MAP_IA_MUESTRAS` (3), `ARA_MAP_IA_MAX_POR_HORA` (30), `ARA_MAP_IA_MAX_SALIDA` (800).

## 9b. Gates before production

1. **Disposable Postgres:** ✅ done (§0c). Optionally repeat on an isolated Neon branch to cover Neon-specific behavior (pooler, TLS, latency), with `--url-env` pointing at that branch.
2. **Real provider** (only if automatic assistance is wanted): after §9's setup, evaluate the chosen model on fictional or approved minimal samples. Record mapping correctness, ambiguity handling, latency and actual cost, kept separate from the simulated result.
3. Then back up Neon, run `scripts/migrate_cloud.py`, deploy, and smoke-test with removable fictional data. This deployment is a separately authorized step.

## 10. Known unsupported layouts and limitations

- One table per import. No unpivoting reports, merging sheets, OCR/PDF, geocoding addresses, resolving Google Maps links, or converting UTM/DMS. These are explained, and their values kept as additional data, never corrupted.
- English and heavily abbreviated headers are not in the curated synonyms. Without assistance they are asked about or kept as additional data (see §8).
- Price questions about an ambiguous «Valor/Importe/Monto» column are always asked, even when assistance is configured. This is intentional, per the brief.
- The cloud draft store's SQL (`DELETE … OFFSET`, `UPDATE … RETURNING`, including the R2 claim) has not run against a real Postgres.
- The cost bound assumes a byte-level BPE tokenizer and a provider that enforces `max_completion_tokens`, which is true of OpenAI's current models. If another provider is added, its bound must be re-derived; any overrun would be recorded whole and flagged, not hidden.
- Repeated headings in a saved format are reconfirmed on every import where they appear; that is the price of not guessing which is which.

### Issues noticed but not fixed (both predate this work)

- **Stray "false" in the header:** the top navigation shows the word "false" in local mode (`web/components/app.js`, header built with native `append`).
- **Phone-width header:** at 375 px the app header is wider than the screen and the page scrolls sideways.

## 11. Files

New: `server/asistente/` (8 modules), `server/api/asistente.py`, `server/repo/formatos.py`, `scripts/evaluar_asistente.py`, `scripts/estado_ia.py`, `tests/test_revision_supervisor.py`, `tests/test_revision_supervisor_2.py`, `web/lib/asistente.js`, `web/components/import/` (assistant, views, preview map, format manager, shared preview parts), `web/styles/assistant.css`, the fixtures and tests listed above.

Changed: `server/db.py` (v6), `server/postgres.py`, `server/staging.py` (`meta` on previews, backward compatible), `server/api/importar.py` (supersession check, provenance, remembering), `server/app.py`, `api/index.py`, `web/lib/api.js`, `web/components/bases/{ImportDialog,BaseGallery}.js`, `web/components/app.js`, `web/components/folders/FolderDialogs.js`, `web/index.html`, `README.md`, `tests/e2e/smoke.mjs`, `tests/test_postgres.py`.

Removed: the pre-preview CSV number-format dialog. The brief rules out a settings dialog on every CSV upload; the convention is now detected or asked.

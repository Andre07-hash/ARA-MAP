# Supervisor review — import assistant

September 24, 2026. Reviewed the implementation on disk and [DEVELOPER_RESPONSE.md](DEVELOPER_RESPONSE.md) against the updated [brief](IMPLEMENTATION_REPORT.md). The developer reported that their own review was still running. This is a review of the inspected snapshot, not acceptance of an unseen final revision. File hashes are recorded in [REVIEW_SOURCE_SNAPSHOT.json](REVIEW_SOURCE_SNAPSHOT.json).

**Decision: the requested interaction is implemented, but do not deploy or enable paid assistance yet.** Five actionable findings below remain. Fold them into the developer's pending review, preserve the accepted workflow and return an updated response. Application code and existing tests were not edited by this review.

## Independently verified

- `env -u DATABASE_URL -u ARA_MAP_DATABASE_URL ./verificar.sh --todo` completed successfully: **488 Python tests run, 8 skipped**, compatibility suite on macOS Python 3.9.6, JavaScript checks, ruff, mypy and **93% coverage**. “488 tests run, 8 skipped” must not be described as 488 executed passes.
- The existing browser suite passed **43/43**, with no console errors, against a separate ephemeral localhost server and disposable SQLite database with AI disabled. That review server was stopped afterward. The developer's server on port 8471 was left untouched.
- The browser checks cover the familiar, unfamiliar-layout and ambiguity journeys plus the existing CSV, folder, map, export and append behavior. These are useful baseline checks, not coverage of the additional cases below.
- Added [review_regressions.py](review_regressions.py): **8 cases; 1 positive control passes, 6 assertions fail, 1 malformed-response case errors** on the inspected code. All use fictional data, temporary SQLite and fake provider responses. No network/provider call is needed.
- No Neon migration, production data mutation, real AI call or deployment was performed. Real Postgres behavior and real-model quality remain unverified, as the developer already disclosed.

Run the additional cases from the repository root:

```sh
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL python3 reports/import-assistant-handoff-2026-09-24/review_regressions.py -v
```

## R1 — P1: remembered duplicate headings can silently exchange total and unit prices

**Location:** `server/asistente/detectar.py`, `_aplicar_formato` (around line 251), with format signatures in `server/repo/formatos.py`.

Reproduction:

1. Import `Terreno,Precio,Precio,Latitud,Longitud` with the row `Norte,1000000,500,19.5,-99.1`.
2. Explicitly assign the first `Precio` to total price and the second to price/m², then remember the format.
3. Import the same headings with the two price columns reordered: `Norte,500,1000000,19.5,-99.1`.

**Actual:** the assistant goes straight to preview, asks no questions and assigns total price **500** and price/m² **1,000,000**. Occurrence number distinguishes two positions; it does not establish that two identically named columns kept their meaning across files. The saved-format path also bypasses the ordinary duplicate-field question because the template already assigns different destinations.

**Required:** automatically reuse uniquely identifiable columns, but require a focused reconfirmation for semantically ambiguous duplicate headings unless additional stable source evidence truly identifies them. Do not infer total vs unit price from magnitude alone. Do not make the boss remap the whole file. Add cases with reordered duplicate/blank headings and preserve the existing unique-header reorder case.

This is an import-data correctness blocker, not a cosmetic problem.

## R2 — P1: latest-revision validation and confirmation are not atomic

**Locations:** `server/api/importar.py`, `_vigente` and `confirm`/`append` (around lines 204, 248 and 305); `server/asistente/servicio.py`, `preparar`/`_responder`.

Confirmation takes a token and checks its draft revision, then performs backup and opens a separate business-data transaction. Another request can successfully prepare a corrected revision between the check and the write. The older confirmation still commits and subsequently deletes the draft.

The regression places a second request at that exact boundary with a controlled test hook: while confirming a preview with total price **1,000,000**, the second request changes that column to additional data and successfully returns a newer preview with **no price**. The first request nevertheless commits **1,000,000**. Both conflicting operations report success. No production concurrency or timing assumptions are needed to reproduce the ordering.

**Required:** atomically coordinate confirmation ownership with draft revision changes and token consumption. Either confirmation claims/freezes the draft first and further preparation is refused, or the correction wins and the old confirmation returns a stale/expired error before business data is written. Do not allow both to succeed. Apply the policy to new-base and append commits in both local and Postgres storage. A second revision check without transaction/ownership coordination leaves another race window.

Retain rollback and destination validation. Add actual concurrent-request controls for the chosen policy as well as the deterministic regression. Do not weaken the test merely because the normal single-dialog UI serializes edits.

## R3 — P1: explicitly foreign prices can be relabeled as MXN

**Locations:** `server/asistente/campos.py`, `_DOLARES`/`moneda` (around lines 115 and 133); `server/asistente/plan.py`, `construir` (around line 120).

Two reproduced inputs:

```csv
Terreno,Precio US$
Norte,1000000
```

```csv
Terreno,Precio EUR
Norte,1000000
```

Selecting the price destination for either column is accepted and builds a terrain with `asking_price=1000000`. The application labels prices as MXN. `US$` is missed because the pattern's final word boundary does not match a trailing dollar sign at the end of the header. EUR is not recognized at all; the current guard only understands USD markers.

**Required:** recognize explicit foreign-currency indicators without relabeling them as pesos. Enforce the same restriction for suggested, remembered and manually selected mappings. Preserve the source amount as additional data or show a clear unsupported-currency outcome. Do not add currency conversion to this correction. Cover `US$`, USD, EUR/€, representative other explicit non-MXN markers, and valid MXN/unspecified legacy peso inputs. Inspect the selected column's relevant values, not just a few preview samples, when explicit currency annotations appear in cells.

The user choosing “price” is not permission to change the currency. This requirement is already in brief section 5.

## R4 — P1 before paid activation: the spending cap is based on an underestimate, and missing usage becomes zero

**Locations:** `server/asistente/ia.py`, `estimar_costo`, `reservar`, `cerrar`, `ProveedorOpenAI.sugerir` (around lines 271, 277, 301 and 375).

`estimar_costo` describes characters/3 as an upper bound, but it is an estimate. It omits the response schema and other request/model overhead from its input calculation. Serializing reservations prevents two callers from spending the same estimated balance; it does not make that estimate a safe upper bound.

A controlled provider response demonstrates the admission/accounting hole:

- Reservation estimate: **$0.0041100**.
- Configured remaining monthly cap: **$0.0041511**.
- Returned usage: 4,000 input tokens and 800 output tokens, within the configured output limit.
- Recorded charge: **$0.0072**, with result `ok`.

These are fake usage figures, not an actual charge or measured real-model token count. They establish that the current code admits a request on an assumed bound and allows reported usage to exceed the cap afterward. The brief's hard-cap claim is therefore unsupported.

Separately, a successful-shaped provider response with no `usage` block is interpreted as zero input/output tokens and releases the reservation as **$0**. Missing metering is not proof a paid request was free.

**Required:** reserve a defensible conservative maximum covering the complete supported request/model format and enforced output allowance, or refuse the request when that maximum cannot be bounded within remaining budget. Record actual usage when trustworthy, but retain a conservative charge/reservation for missing or invalid usage. Validate nonnegative usage/pricing, handle incomplete/invalid/refused responses consistently, and preserve the reservation on uncertain failures. Do not “fix” an overrun by hiding it or clipping the ledger to the cap. Add tests for underestimated input, missing/malformed usage, simultaneous calls and restart persistence. Keep the pre-call authorization and budget logic outside long-held database transactions.

## R5 — P2: a malformed AI value escapes fallback and aborts analysis

**Location:** `server/asistente/ia.py`, `validar` and `sugerir` (around lines 237 and 318).

With a provider result containing `{"columna": [], "campo": "terreno", "motivo": "malformed"}`, `validar` tests membership in a set before checking that the column ID is a string. Python raises `TypeError`; `sugerir` catches only `FallaIAError`, so the whole analyze request fails instead of returning the deterministic questions. The regression exercises this through `api.analizar`, not only the validator.

**Required:** validate primitive types before membership/lookup operations and normalize malformed provider data to the documented invalid-response fallback. Cover arrays/objects/null in column/field IDs and invalid top-level/envelope values. Continue to surface unexpected internal bugs to maintainers without exposing uploaded contents, but do not let an external malformed response destroy an otherwise readable import. Verify reservation accounting for these failures as part of R4.

## Remaining verification and presentation notes

1. **Real Postgres is a deployment gate.** Run the prepared disposable-schema integration tests, migrations from existing folder-enabled data, cross-worker draft/revision controls and backup/restore checks against disposable Postgres. A migration script and mocked SQL are not substitutes. Do not use production Neon as the first test of new SQL.
2. **Real-provider testing is a paid-assistance gate.** After R4/R5 and administrator configuration, evaluate the selected model with fictional/approved minimal samples and record actual mapping correctness, ambiguity handling, latency and cost. The simulated 35/37 result is correctly labeled and must remain separate from model accuracy.
3. The stray navigation `false` and mobile header overflow are developer-reported pre-existing issues. They are not new reproduced findings in this review. Include them in final UI triage; neither substitutes for resolving the data/cost bugs above. The no-AI-button and targeted-question experience should stay intact.
4. No extra product features are requested. Existing accepted CSV/folder/map work should remain intact. Keep final documentation clear about which checks actually ran, which were skipped and which provider was simulated.

## Return criteria

Address R1–R5, preserve current assertions and add these regressions (or equally strong controls) to normal verification. Re-run affected checks and the complete suite on the final implementation after the developer's own review finishes. Update `DEVELOPER_RESPONSE.md` with each correction, current test results and outstanding environment setup. Identify the final source revision or file hashes so later review is against stable code.

The interaction design is on target. Acceptance of the implementation and production rollout remain pending the correctness fixes and the relevant verification gates above.

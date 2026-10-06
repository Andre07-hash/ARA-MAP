# ARA Map — developer assignment: connected Excel and BigQuery

> **Priority 0: GitHub/Vercel readiness now comes first.** Follow the [repository and deployment prerequisite](../github-vercel-readiness-2026-10-05/START_HERE.md) before continuing Excel + BigQuery implementation. The owner requested this order after moving development to GitHub.

Issued October 5, 2026 following the owner's instruction to proceed with the revised plan. Status: implementation packet prepared; developers have not been dispatched by this task. No implementation, cloud provisioning, migration or deployment is claimed here.

## Required result

Employees use ordinary Excel files, share them through their drive and grant ARA Map access once. A signed-in team user clicks **Actualizar desde Excel**; ARA Map retrieves the latest saved version, validates and stores it in company BigQuery, then displays the updated live map and table. No repeated file selection, upload or replacement workbook is required. This must work while the owner's Mac is off.

These two requirements are the next milestone. Defer the old Stage 2 public catalog, additional website editing, publication features, AI search, shortlists and other enhancements. Preserve completed work and existing privacy rules. Do not resume the old stage sequence.

Read next:

1. [Shared contract](CONTRACT.md).
2. [Developer assignments and ready-to-use prompts](ASSIGNMENTS.md).
3. [Acceptance and migration checks](ACCEPTANCE.md).
4. [Company setup inputs](COMPANY_SETUP.md).

Background: [owner realignment](../product-plan-2026-10-05/EXCEL_BIGQUERY_REALIGNMENT.md). Old inventory packets are historical context only where consistent with this assignment.

## Build order

| Step | Work | Evidence needed to advance |
|---|---|---|
| 1. Establish the connection design | Identify drive provider and file/table; settle stable row ID; identify BigQuery test destination, access, operational storage and execution host | `CONNECTION_DECISIONS.md` records chosen provider, authentication, storage responsibilities, deployment/runtime approach and real access status; no secret values |
| 2. Prove the full backend path | One representative shared XLSX → authenticated fetch → existing parsing/validation → versioned BigQuery data → API read | Real provider and real test BigQuery evidence for two workbook versions; source version, job IDs, counts and selected field checks |
| 3. Deliver the user workflow | Connect once, preview/mapping, Refresh, progress/results, live map/table and recovery | Integrated browser demo against the real backend; mocks clearly separated |
| 4. Verify and rehearse migration | Concurrent refreshes, failures, identity, private data, existing records and historical maps | `VERIFICATION_RESPONSE.md`, field reconciliation, recovery rehearsal and tested source revision/manifest |
| 5. Controlled cutover | Deploy the verified candidate against the designated company destination; verify from a second computer | Approved destination/access, passing prior gates, backup/rollback plan and live evidence; no deletion of original stores |

Interface work and verification preparation can proceed while the backend is built. Do not present fixture results as provider, BigQuery or deployed acceptance. Missing company access blocks the real connection gate, not local contract, parser, interface or test work.

## Scope and execution

Use the current Python backend and JavaScript/Leaflet interface. Reuse Excel parsing, interpretation, validation and map presentation. Add a dedicated BigQuery business-data repository; do not mechanically translate SQLite/Postgres SQL or rewrite the entire app.

The immediate acceptance surface is the authenticated current map/table. Connected data is not automatically public. Website edits to Excel-owned fields must be disallowed on the server and explained in the interface. Existing standalone records can retain their existing behavior.

Ordinary development and disposable tests should proceed without repeated owner confirmations. Production changes need a concrete destination and working company access; never guess these or treat production as a test fixture. Make a reviewable migration/release candidate first and identify any remaining business decision precisely. Do not request broad approval for routine implementation choices.

The packet authorizes no deletion of existing databases, workbooks or snapshots and does not authorize making records public. Do not create new paid infrastructure without presenting the concrete requirement. Keep credentials out of source, reports and browser responses.

Completion means both connected Excel and company BigQuery work together. A Refresh button backed by mocks, another upload workflow, or a BigQuery analytics copy while Neon remains authoritative does not meet the assignment.

## Existing code to inspect

- `server/importer.py`, `server/asistente/`, `server/validation.py`: XLSX interpretation, preview and validation.
- `server/api/importar.py`: existing file upload flow, not a persistent connection.
- `server/db.py`, `server/postgres.py`, `server/auth.py`: storage and operational auth dependencies.
- `server/repo/mapas.py`: historical snapshots; existing refresh copies already imported bases.
- `server/api/inventario.py`, `server/repo/inventario.py`: accepted draft-inventory work and old publication placeholders.
- `server/app.py`, `api/index.py`: routing, sign-in and cloud adapter.
- `web/components/`, `tests/`, `tests/e2e/`: interface and existing regressions.
- `vercel.json`: currently declares a 120-second function maximum. Verify actual hosting limits before choosing an execution design.

All paths above are relative to the workspace root `/Users/andrejasso/Desktop/ARA Map`.

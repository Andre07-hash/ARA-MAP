# Work assignments

> **Priority 0: GitHub/Vercel readiness now comes first.** Follow the [repository and deployment prerequisite](../github-vercel-readiness-2026-10-05/START_HERE.md) before continuing Excel + BigQuery implementation. The owner requested this order after moving development to GitHub.

Use one developer per workstream if available, or execute sequentially with the same contracts. These are assignments prepared for handoff, not a claim that agents or external developers have started. Each response must distinguish implemented, verified with real services, fixture-only, blocked and not attempted.

## Backend/data developer

Own `server/`, `api/`, backend dependencies, schema/setup/migration tools and backend tests. Coordinate `server/app.py` route changes with the interface developer through CONTRACT.md; the interface developer does not edit backend files.

1. Inventory current auth, legacy bases/maps, inventory code and cloud adapter dependencies. Produce `CONNECTION_DECISIONS.md` with chosen provider/auth, stable IDs, BigQuery schema, operational-state store, job execution and deployment configuration. Record missing company inputs; do not load guessed production credentials or create an unapproved provider integration.
2. Define source connector and BigQuery repository interfaces and fictional XLSX fixtures. Continue locally while company access is pending. Keep provider implementations bounded to the chosen service.
3. Build authenticated file retrieval, source-version detection, table/mapping setup and permanent identity validation. Reuse existing parsing/validation. Provide practical setup for the ID column if none exists.
4. Build versioned BigQuery batch ingestion, current-version activation, audit/results, idempotency and recovery. Verify real transactions, job retries and concurrency against an explicit test dataset. Do not depend on BigQuery enforcing keys or SQLite-like SQL.
5. Implement the source/run/read endpoints and integrate authentication, read-only mode and Excel-owned-field write protection. Prove live reads use BigQuery; any cache must be reconstructible from it. Preserve standalone legacy behavior.
6. Add operational setup and reversible migration tooling with explicit target parameters, dry-run inventory/reconciliation and backups. Cover both the actual local starting schema and current cloud state, not only synthetic latest-schema fixtures. Preserve maps and source lineage. Supply hosting/runtime compatibility evidence.

Return `BACKEND_RESPONSE.md`: changed paths/revision, endpoint examples, test commands/results, real provider + BigQuery evidence, unresolved dependencies, migration plan and measured query/refresh behavior. Supply sanitized fixture/result files, not production records or credentials.

Ready-to-use prompt:

> Implement the backend/data work in reports/excel-bigquery-developer-handoff-2026-10-05/START_HERE.md, CONTRACT.md and ASSIGNMENTS.md in /Users/andrejasso/Desktop/ARA Map. Deliver connected ordinary Excel → validated versioned company BigQuery data → authenticated live reads. Follow the contract and file ownership. Use disposable targets; preserve original data and completed inventory work. First record provider, identity, operational storage and durable execution decisions. Continue interfaces, local code and fictional tests while access is pending, but never call mocks a verified cloud integration. Return CONNECTION_DECISIONS.md and BACKEND_RESPONSE.md with evidence. Do not resume the old public-catalog stage.

## Interface developer

Own `web/`, frontend tests and user-flow browser fixtures. Work from CONTRACT.md; coordinate API adjustments before coding incompatible payloads.

1. Add **Conectar Excel** in the existing Bases/data-source navigation. Show the connection/access step, table choice, interpretation preview and ID-column selection. Use ordinary user language; no project IDs, SQL or credential textboxes in the employee flow.
2. Add a connected-source card: workbook name, selected table, connection state, last successful refresh and **Actualizar desde Excel**. Link to the source file only through a safe provider URL. Keep upload available for standalone historical data.
3. Implement actual run polling/status and recovery actions. On reload or browser reopen, recover the run from backend state. Avoid duplicate requests while a source is refreshing. Show successful no-change results, added/updated/removed counts and row-specific issues. Errors retain the previous map/table and its timestamp.
4. Integrate source-backed terrain DTOs with existing map, filters, table, details and applicable exports/saved-map creation. Use the same returned version throughout; show a clear distinction between a live Excel source and a dated saved map. Do not accidentally route this action through the old saved-map refresh.
5. Explain that connected values are edited in Excel; the backend must enforce that restriction too. Provide a clear review step for unexpected empty data or changed mapping. Ordinary valid updates require just Refresh after saving Excel.
6. Verify keyboard access, readable states and phone layout. Exercise success/failure and reconnect against the real backend once available; label fixture-only demonstrations honestly.

Return `FRONTEND_RESPONSE.md`: screenshots, tested flows, API dependencies, changed paths/revision, test results and remaining limitations.

Ready-to-use prompt:

> Implement the interface work in reports/excel-bigquery-developer-handoff-2026-10-05/START_HERE.md, CONTRACT.md and ASSIGNMENTS.md in /Users/andrejasso/Desktop/ARA Map. Build connect-once Excel setup, Actualizar desde Excel, persistent refresh status/results and live map/table integration using the current interface. Own web/ and frontend tests; coordinate through the contract without editing backend files. Begin with explicit contract fixtures, then demonstrate the real backend flow. Preserve dated maps and existing privacy. Return FRONTEND_RESPONSE.md with evidence. Other product features remain deferred.

## Verification/release developer

Own independent scenarios and evidence under this packet's `verification/`. Prepare cases immediately; execute cloud cases after backend integration and access exist. Report implementation defects to their owner; if the same person fixes them, rerun the independent scenario and record the patch.

1. Turn ACCEPTANCE.md into reproducible checks and independently constructed workbooks/expected values.
2. Verify real provider → backend → actual BigQuery tables → browser results, including second-session reads. Check stored data directly instead of accepting UI counts as proof.
3. Exercise repeat requests, two refreshes racing, worker interruption, source modification during fetch, access revocation, schema changes and empty/partial input. Confirm last good version survives.
4. Verify IDs, currency/precision, missing-coordinate handling, removals/history and source isolation. Test anonymous access and credential/source metadata leakage.
5. Rehearse migration on copies, reconcile fields and historical maps, and demonstrate recovery. Use at least 100 representative terrains and three signed-in sessions as the existing baseline; separately measure realistic workbook size and refresh duration.
6. Provide a release recommendation from actual evidence, with the exact candidate revision/manifest and explicit skipped/blocked cases. Never certify fixture-only provider/BQ tests as production readiness.

Return `VERIFICATION_RESPONSE.md` plus sanitized evidence, candidate manifest, migration reconciliation and a concrete cutover/rollback checklist. The controlled live check requires another computer and the owner's Mac off; simulated disconnection is useful but not equivalent evidence.

Ready-to-use prompt:

> Independently verify the Excel + BigQuery milestone described in reports/excel-bigquery-developer-handoff-2026-10-05/START_HERE.md, CONTRACT.md and ACCEPTANCE.md in /Users/andrejasso/Desktop/ARA Map. Prepare scenarios while implementation proceeds, then test real drive access, real BigQuery persistence and the integrated browser flow on disposable targets. Include identity, failures, concurrency, privacy, old-data migration and recovery. Do not accept UI mocks or developer claims as service evidence. Return VERIFICATION_RESPONSE.md with pass/fail/blocked results, reproducible evidence and candidate revision/manifest. Do not publish real data or delete original stores.

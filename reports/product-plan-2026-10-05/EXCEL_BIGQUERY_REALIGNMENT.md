# ARA Map — Excel refresh and company BigQuery take priority

> **Priority 0: GitHub/Vercel readiness now comes first.** Follow the [repository and deployment prerequisite](../github-vercel-readiness-2026-10-05/START_HERE.md) before continuing Excel + BigQuery implementation. The owner requested this order after moving development to GitHub.

**Current implementation instructions:** [Excel + BigQuery developer packet](../excel-bigquery-developer-handoff-2026-10-05/START_HERE.md). The owner has asked to proceed with this plan. Assignments, shared contract, company setup inputs and acceptance criteria are ready; no developer dispatch or software completion is claimed by this notice.

Owner direction received October 5, 2026, after a partner meeting. This report supersedes the previous delivery order and the assumption that website editing is authoritative. It records direction and a proposed implementation approach; the connector and BigQuery migration have not been implemented.

## Before this interaction

The previous SUPERVISOR_PLAN.md made the website the main place employees maintain inventory, retained Excel for bulk uploads, and explicitly deferred spreadsheet synchronization. START_HERE.md kept SQLite/PostgreSQL and excluded a database-provider change. The next assignment was Stage 2 publication and public catalog, followed by reviewed Excel additions.

The latest saved supervisor review records accepted Stage 1 development: individual sign-in, stable inventory identity, draft create/edit/read, history and conflict handling. It records no completed Stage 2 delivery and no deployment of that inventory work. This interaction inspected source and saved reports; it did not rerun that verification or audit the current production service.

We were aligned on a shared terrain inventory and avoiding repeated manual uploads, but materially misaligned on the mechanism, storage provider and delivery order. The earlier plan avoided uploads by moving editing into the website; the owners now want a lasting Excel connection and company BigQuery storage.

## Current storage and refresh behavior

- The local default database is `datos/ara_map.db`, selected in `server/db.py`; an environment override is possible. That file exists on this Mac.
- The documented deployed version stores shared data in Neon Postgres. `api/index.py` requires a configured Postgres connection; it does not fall back to local SQLite. This is supported by source and deployment documentation, not a fresh inspection of cloud configuration today.
- The local and deployed databases are separate. The README describes a one-time migration, not ongoing synchronization.
- Imports read uploaded Excel/CSV bytes. A remembered import format remembers interpretation, not a connection to the workbook.
- Saved-map Refresh in `server/repo/mapas.py` copies records from already imported bases. It does not retrieve the latest Excel file.
- No BigQuery or persistent Excel-source integration was found in the inspected application code.

## New immediate scope

1. Connect an Excel source once. When an authorized user clicks Refresh in ARA Map, read its latest saved data and reflect changes without selecting or uploading another file. The owner clarified that employees should use ordinary Excel files, share them and keep them on their drive, with ARA Map granted access. Do not require a special replacement spreadsheet application. The specific drive provider is still unspecified.
2. Persist the shared terrain data in the company's BigQuery and make the deployed app independent of this Mac.

Treat these as one end-to-end milestone. Public-catalog expansion, publication workflows, additional website editing, client shortlists, AI search and other feature development follow this milestone. Preserve existing work without extending the old stages ahead of these priorities. Existing privacy rules and historical saved-map preservation still apply.

## Proposed flow

Shared Excel workbook → server-side source connector → validation and change reconciliation → company BigQuery → ARA Map's current map/table.

Excel is the proposed editing source for connected fields; BigQuery is the durable company store consumed by ARA Map. Do not create independent website edits to those same fields without an explicit conflict/writeback design. Two-way synchronization is not implied by this request. If another system already feeds Excel, identify that upstream process; reading a saved workbook does not itself refresh its external data connections.

For Microsoft 365, a workbook in company OneDrive or SharePoint can be accessed through Microsoft Graph. Select the file/table once and retain its stable source identity and approved column mapping. Confirm the company's authentication model before choosing workbook endpoints versus authenticated file download with the existing parser. Do not assume all Graph endpoints support the same permissions.

A workbook available only on a computer cannot be fetched by a cloud service when that computer is off. To meet the independence requirement it needs a company-accessible shared location or an existing cloud publishing process. The owner confirmed an ordinary employee-shared Excel file on their drive; the exact drive service and file location remain to be identified. Use a one-time link/file selection plus access grant appropriate to that provider, then retain the connection for subsequent refreshes.

On Refresh, the backend should retrieve a consistent saved source version, validate it, reconcile changes using permanent terrain identifiers, commit a complete successful version to BigQuery and then reload the live view. Refreshing the same version twice must not create duplicates. Renaming or reordering a row must not create another terrain. New, edited and removed rows need explicit handling; proposed removal behavior is to remove them from the current source view while retaining history. Reject ambiguous duplicate/missing identifiers instead of guessing.

Show last successful refresh, source version where available, and added/updated/removed counts. If access, validation or the write fails, retain the previous successful data and show the failure. Avoid replacing valid data with an empty or partial fetch. Preserve currency, numeric precision, additional source fields and provenance. Dated saved maps remain dated snapshots; a live-source refresh must not silently rewrite past presentations or bypass publication/privacy rules.

## BigQuery design and migration

BigQuery becomes the durable store for the synchronized terrain dataset and its synchronization history, rather than merely an analytics copy left behind Neon as the business-data authority. Establish company project, dataset, region and a backend identity with approved access. Credentials stay on the server.

This is not a connection-string substitution. Current repositories depend on SQLite/Postgres SQL, relational behavior and application transactions. BigQuery is an analytical warehouse; Google recommends batching updates rather than treating it as a transactional application database. Implement a dedicated data-access path for versioned refresh batches and measure map-read latency and query cost. Decide explicitly where account/session state and other operational metadata live; do not claim BigQuery has replaced every application storage concern without designing and testing those paths.

Inventory the actual local and cloud datasets, distinguish current inventory from demos and historical versions, and reconcile them before migration. Rehearse on a separate destination, compare row counts and important fields, preserve saved maps and retain recovery copies. Do not retire Neon or the local database until the company-backed flow is verified. This report does not perform or authorize deletion of either source.

## Implementation order and acceptance

1. Identify the shared workbook/table, stable terrain key, upstream feed if any, and approved BigQuery destination/access.
2. Build one complete Refresh path with a representative workbook and test dataset, reusing the existing parser/validation where suitable.
3. Add the connection setup, refresh status, change summary and recovery behavior; connect live map/table reads to the company data.
4. Rehearse migration, then validate the deployed flow before switching the working dataset.
5. Resume later product plans only after this milestone works.

Acceptance: edit a price and coordinates in the shared workbook, add a terrain and remove one; save; click Refresh once. BigQuery and the live map/table must agree, preserve identity/currency and correctly reflect each change. Repeat Refresh without duplicates. Test row reordering, invalid input, revoked source access, interrupted writes and two simultaneous refreshes. Demonstrate another authorized computer sees the successful result while this Mac is off. Historical saved maps retain their intended contents. Record measured refresh duration and map-read performance rather than promising instantaneous updates.

## Inputs still needed

- Where the workbook lives, which table is authoritative, and whether an upstream API/system populates it.
- Company's Google Cloud project/dataset/region and an approved service identity; user access to the console alone does not establish application access.
- Stable terrain identifiers, or an agreed one-time assignment retained in Excel.

No secrets are needed in chat. There was no application-code change, database migration or deployment during this review. Only planning and handoff documents were updated.

## Evidence

Local: `README.md`, `server/db.py`, `server/postgres.py`, `api/index.py`, `server/api/importar.py`, `server/repo/mapas.py`, `SUPERVISOR_PLAN.md`, and `../inventory-developer-handoff-2026-10-05/SUPERVISOR_STATUS_REVIEW.md`.

Official integration references checked for this report:

- [Microsoft Graph Excel support](https://learn.microsoft.com/en-us/graph/api/resources/excel?view=graph-rest-1.0)
- [Microsoft Graph file download and permissions](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0)
- [BigQuery overview](https://docs.cloud.google.com/bigquery/docs/introduction)
- [BigQuery update and query performance guidance](https://docs.cloud.google.com/bigquery/docs/best-practices-performance-compute)

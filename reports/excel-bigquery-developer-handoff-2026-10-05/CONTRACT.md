# Connected-source contract v1

This is the integration baseline. Developers may refine internal implementation, but must record interface changes here before dependent work adopts them. Provider selection is unresolved; implement the company's first chosen provider, not several speculative integrations.

## Source and identity

One connection identifies a provider, stable file ID, worksheet/table, interpretation version, stable terrain-ID column and credential reference. A display filename/path is not identity. Keep mapping/configuration versions in the ingestion fingerprint so the same bytes can be reprocessed after an interpretation fix.

Excel supplies the authoritative values for connected terrain fields. BigQuery holds their durable current and historical versions. Neither a browser nor local SQLite is authoritative for this dataset. No bidirectional Excel writeback in this milestone.

Use an existing unique company terrain ID if available; otherwise arrange a permanent ID column in the same ordinary workbook as part of initial setup. Define how employees obtain an ID for new rows. Do not infer identity from row number, name, coordinates or price. Do not silently regenerate IDs on refresh. Missing/duplicate IDs block activation and identify the affected rows. Preserve strings with leading zeroes.

Scope row identity by source unless company IDs are confirmed globally unique. Do not silently merge terrains from different files. Reject duplicate registration of the same provider file/table, or return the existing connection. Replacement with a different file ID requires an explicit reconnect/review operation.

## Fetch and interpret

Use provider-authenticated APIs and stable file IDs. A shared link helps identify a file; it does not bypass its permissions. The backend reads the latest saved cloud workbook, not unsaved desktop edits. Reading XLSX does not execute macros or refresh upstream Power Query/API feeds. Document how formula results are supplied and detect unsupported/unavailable cached results before accepting affected data.

Fetch one consistent file version, with revision/ETag checks or equivalent provider guarantees, and retain its content hash. If source changes during a multi-request fetch, retry safely instead of assembling mixed versions. Reuse the existing XLSX reader where appropriate; resolve initial table/header/unit/currency ambiguities in setup and save that interpretation. A later incompatible schema change requires review; never guess silently.

Missing coordinates remain valid stored records with existing warnings and no plotted location. Invalid IDs, unreadable content, ambiguous changed mappings and incomplete fetches block activation. Do not convert missing prices to zero or infer currency. Preserve raw source values/provenance needed to audit parsing. Use a documented decimal representation for prices without introducing rounding beyond the stored source precision.

## Versioned storage and activation

Logical entities (physical DDL is backend-owned):

| Entity | Responsibility |
|---|---|
| Connected source | Source/configuration identity; current successful version reference; last successful refresh metadata |
| Sync run | Run ID, source/config version, actor, request key, status, provider version, hash, timing, counts, safe error and BigQuery job references |
| Terrain version | Source ID + dataset version + terrain ID; typed business values, extra fields, warnings and provenance |
| Source history | Successful source versions and changes/removals, sufficient for audit and recovery |
| Saved maps and migration lineage | Preserve dated terrain values/currencies, layer identity/configuration and original source references independently of live refresh |

Load a complete candidate batch without exposing it. Validate identity, row counts and parse completeness. Activate the candidate atomically only after all required data is durable. Use a guarded update of the source's current version and handle competing transactions/retries. Readers resolve one version for each response and pin it across map/table pagination; no mixed-version views. An older/slower refresh must not replace a later successful refresh.

BigQuery constraints are not a substitute for application uniqueness validation. Define deterministic request/job identities and transaction/retry behavior. No in-process lock or local file may be the sole concurrency protection in a multi-worker deployment. A timeout with unknown commit outcome must inspect durable run/job state before retrying. A repeated successful request returns its recorded result.

Compare business fields for counts: added, updated, removed, unchanged. Reordering alone changes no terrain identity or business value. Rows absent from a complete valid source version disappear from that source's live view, but history and dated maps survive. This does not assert that a removed terrain was sold. An unexpectedly empty dataset requires a clear explicit review before activation; network/permission errors can never be interpreted as an empty workbook.

An unchanged source plus unchanged interpretation creates no duplicate data version. Update the last checked/success metadata so users can distinguish a successful no-change refresh from a stale connection. Caches are derived, version-keyed and invalidated on activation; BigQuery remains authoritative. Retention must not remove data referenced by saved maps or recovery requirements.

## Application state and execution

Before integration, document storage responsibilities in `CONNECTION_DECISIONS.md`: business data/history/snapshots in company BigQuery; secrets in a server-side secret facility; accounts/sessions and durable job coordination in an explicitly identified operational store. Existing Postgres can support development/transition, but disclose exactly what remains there. The request does not settle whether every operational service must move into the company's Google Cloud; ask that narrowly before cutover if required. No hidden business-data authority in Neon and no dependence on the owner's Mac.

A refresh job must survive browser closure, worker restart and request timeouts. Select an actual supported durable execution mechanism after evaluating the existing host; returning HTTP 202 and starting an untracked background thread is insufficient. If using BigQuery jobs and resumable request-driven orchestration, document who resumes each non-BigQuery step and demonstrate completion/recovery. Any new worker service must have its hosting/access/cost implications stated before provisioning.

## API baseline

All routes below require existing authenticated team access, obey read-only mode where applicable and return no tokens or private provider download URLs. Route names are new; the old saved-map refresh retains its historical meaning.

| Method/path | Request/result |
|---|---|
| `POST /api/fuentes/analizar` | Provider file reference; inspect access, available tables and suggested interpretation; return expiring setup ID and preview. Does not activate terrain data. |
| `POST /api/fuentes` | Setup ID + selected table, confirmed mapping and ID column + request key; create/reuse persistent connection. Return source DTO. |
| `GET /api/fuentes` and `GET /api/fuentes/:id` | Source DTOs: ID, label, safe provider/file identity, connection state, current version, last successful refresh, active run ID. |
| `POST /api/fuentes/:id/actualizar` | `Idempotency-Key` header, no uploaded file. Return `202` with durable run ID/status, or recorded completed result on replay. Same source already refreshing returns its active run. |
| `GET /api/fuentes/:id/ejecuciones/:run_id` | Run status and safe progress/result, warnings, counts, current/previous version and retry/review action if applicable. |
| `GET /api/fuentes/:id/terrenos?version=…&cursor=…` | Authenticated terrain DTOs, warnings, consistent source version and pagination. Existing rendering may adapt these DTOs. |

Provider OAuth endpoints depend on chosen provider/auth model; record their exact contract before frontend implementation. Reconnect/configuration review must use version checks and never clear good data. Add concrete routes for those actions to this contract when finalized. Shared errors use `{error:{code,message,retryable,details?}}`; details never include secrets. Preserve existing API formats on unchanged routes.

Run states: `queued`, `fetching`, `validating`, `writing`, then `succeeded`, `unchanged`, `needs_review` or `failed`. Activation occurs before reporting success. Include nullable `finished_at`, result counts and last successful version. The backend owns status; UI must not simulate percentages.

## Access and continuity

All signed-in team members keep equal application capabilities. Company source permissions control the connector's access; distinguish expired credentials, revoked access, moved/deleted files and transient errors. Restrict authenticated fetches to the chosen provider's supported endpoints and validate links/redirects; no arbitrary server-side URL fetcher. Follow the existing origin protections for mutations.

Connected records and source metadata remain internal. No refresh publishes records, exposes imported contact/notes fields, changes existing anonymous route policy or rewrites historical maps. Enforce Excel-owned-field restrictions on every applicable write route, not just in disabled controls.

## Official references

- [Graph file content and permissions](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0)
- [Google Drive file download](https://developers.google.com/workspace/drive/api/guides/manage-downloads)
- [BigQuery transactions and conflicts](https://docs.cloud.google.com/bigquery/docs/transactions)
- [BigQuery key constraints](https://docs.cloud.google.com/bigquery/docs/primary-foreign-keys)
- [BigQuery batching guidance](https://docs.cloud.google.com/bigquery/docs/best-practices-performance-compute#avoid_dml_statements_that_update_or_insert_single_rows)

References checked when this packet was written; verify endpoint-specific permissions/runtime support for the selected implementation.

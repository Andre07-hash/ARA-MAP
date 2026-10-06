# Acceptance and migration

Record each case as PASS, FAIL, BLOCKED or NOT RUN with evidence and environment. Passing offline tests does not pass real provider/BigQuery checks. All original workbooks and databases remain preserved.

| ID | Scenario | Required result |
|---|---|---|
| E01 | Connect an ordinary shared XLSX once | Stable provider file/table connection saved; initial preview/mapping accepted; no recurring upload |
| E02 | Save price and coordinate edits; add and remove a row; Refresh | BigQuery and live map/table match the expected fields and counts; removed row retained in history |
| E03 | Refresh unchanged source twice; replay same request key | No duplicate terrain/version; recorded result and last-checked time remain truthful |
| E04 | Rename terrain, reorder rows, use leading-zero IDs | Identity preserved; reorder alone is not a business update |
| E05 | Missing/duplicate ID, renamed ID column or ambiguous mapping | Actionable row/configuration review; previous successful data remains active |
| E06 | Two connected files contain similar terrain names/IDs | Correct source isolation; no guessed merge or duplicate source registration |
| E07 | XLSX renamed/moved or replaced with another file | Stable identity works where provider supports it; replacement requires reconnect/review, no silent source swap |
| E08 | Access expired/revoked, file deleted or provider times out | Safe error and recovery; no empty replacement or false success |
| E09 | Workbook changes during fetch; partial/invalid/empty data | Consistent saved version or explicit failure/review; no destructive partial activation |
| E10 | BigQuery load/activation fails; network timeout after commit | Last good data survives; inspect durable result and safely recover without duplicate activation |
| E11 | Two refreshes race; older run finishes last | No newer-version regression, no mixed map/table version and no duplicate business records |
| E12 | Close browser/restart worker after Refresh | Work resumes/completes through the documented durable mechanism; visible run status survives |
| E13 | USD/MXN, decimal prices, null price and missing coordinates | Preserve values/currency; no FX conversion; missing locations stored with warnings and not guessed |
| E14 | Cached formulas or upstream data connections | Explicit supported semantics; never promise API fetch recalculates desktop queries/macros |
| E15 | Attempt website/API edit of connected Excel-owned fields | Server rejects the conflicting edit and interface directs employee to Excel |
| E16 | Anonymous request; malicious file URL; inspect responses/logs | No internal source/data/secrets exposed; no arbitrary URL fetch; mutations require valid auth/origin |
| E17 | Refresh then reopen saved historical map/export | Historical values and currencies remain intact; current-source displays show the new version |
| E18 | Reload app, second authorized session, clear derived cache | Successful version reloads from BigQuery; no dependency on local dataset or authoritative Neon mirror |
| E19 | 100+ representative terrains, three sessions, realistic XLSX | Measured refresh/load duration, bytes processed and cost estimate; no silent data loss; capacity claims limited to evidence |
| E20 | Company-hosted deployment, second computer, owner's Mac off | Connect/refresh/read flow still works; proves required independence |

## Migration rehearsal

1. Inventory actual local schema/version, local bases/maps, cloud bases/maps and any new inventory records. Identify demos, duplicate historical sources and the authoritative working workbook. Do not merge by name.
2. Back up and restore to isolated copies. Target project/dataset and any operational test store must be explicit; missing configuration must fail closed, never fall back to production.
3. Produce migration mappings from old identities to retained/new IDs. Preserve source provenance, field values, currencies, nulls, additional data and saved-map layer/configuration content. Historical maps may embed their own frozen data rather than rely on live-source pointers.
4. Reconcile counts and all migrated business fields, plus saved-map content/configuration. Explain any deliberate exclusions. Test actual old local schema migration, not just recent synthetic schemas.
5. Demonstrate rollback to the prior active source version and restoration of migrated snapshots. In-flight runs must not reactivate obsolete data after rollback; operational sessions/credentials follow their separate recovery rules.
6. Record exactly what remains in each service after cutover. Do not claim all company data is migrated if historical business data remains dependent on the Mac. Any retained Neon operational state must be explicitly listed.

## Cutover evidence

Use the verified candidate, designated company dataset and approved application identity. Capture pre-cutover backups and reconciliation, complete the final migration, then demonstrate E02/E03/E18/E20 against the deployed service. Provide rollback steps and the last known-good version. No old store is deleted as part of this assignment.

Timing and query-cost results must be measured before making a production-performance promise. If access or infrastructure is missing, return the completed local deliverables and the exact blocked acceptance cases; the milestone remains incomplete.

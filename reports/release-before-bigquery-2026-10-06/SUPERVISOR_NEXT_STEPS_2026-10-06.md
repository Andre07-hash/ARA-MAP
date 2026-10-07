# Next steps: get the real workbook connected, then release

> **Paused by the owner's later direction:** use the [master-table product plan](../master-table-plan/MASTER_PLAN.md) for current work. The Excel connector is retained for future use. The assignments and release ordering below are historical and must not drive the new milestone.

Supervisor review, October 6, 2026. Read this first. It narrows and supersedes conflicting process requirements in the completion instructions at `3c486f9`; the existing data-preservation and credential protections remain applicable.

Reviewed: PR #6 implementation `415eb2640a42d99687fcef7a68ac3575ce8a651e`, completion report `9d452790b4f22a59e9d904d3403be4153cbd810a`. This was a focused source/report review, not an independent execution of the test suite or a hosted acceptance run. The reported local tests are substantial; they do not establish real Microsoft or Vercel compatibility. GitHub CI at report commit `9d45279` passed both JavaScript and Python/disposable Postgres ([run 37544275784](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37544275784)).

## Scope and decisions — proceed without another design approval

The next milestone is a working Preview where the owner signs in with the ARA Microsoft work account, selects the existing workbook in that account's OneDrive for Business, and refreshes saved changes. The owner supplied a company OneDrive workbook, so prioritize that account type. Do not insist on creating a separate personal account. Do not put the workbook's sharing URL or actual data into GitHub reports. The first release uses the owner's file picker, not pasted-link resolution or arbitrary SharePoint library browsing.

Keep Neon, the current connector architecture and Spanish UI. BigQuery and KMZ are future work. Do not add background workers, general permission management, self-service account onboarding, broad catalog features, or another architecture rewrite for this release.

Answers to the four questions in the completion report:

1. **Single-request Refresh: accepted for this release, conditional on hosted results.** Measure the real workbook's initial connection and refresh on the actual Vercel configuration. File size alone does not establish execution time. Check successful completion within the lease/function limits, preservation of previous data on interruption, and ability to retry. Add a simple total deadline only if needed; introduce a worker only if the real workload cannot fit. Do not describe closing a tab as guaranteed server cancellation.
2. **Public continuity: implement the narrow legacy manifest.** Preserve the previously public bases, saved maps, fields and export behavior. Derive the exact set from the verified legacy backup and compare it against the old behavior. New connected bases remain private. This implements the standing requirement to preserve the existing site; no new yes/no question is needed. No broad public-catalog project.
3. **Database write freeze: accepted as the operational mechanism, subject to one Neon rehearsal.** Verify actual pooled/direct connections and the old code cannot write while frozen. A default read-only setting is not an immutable security boundary. Do not redesign it if the deployed connections honor it. Correct the release sequence below before using it.
4. **Integrate on the feature branch first.** Incorporate PR #4 into PR #6's branch without first merging either into main. Preserve its history or clearly document the imported commit. Resolve only necessary conflicts. Keep automatic production deployments disabled. Produce one integrated candidate SHA with the inventory fix, connector, public continuity and necessary rehearsal updates. Once reviewed, merge in a documented order that avoids duplicate changes; close a superseded PR only after its changes are accounted for.

## Two concrete corrections

### File selection must not silently omit later pages

At `415eb26`, `server/excel/microsoft.py::Graph.listar` requests 200 items and reads only `value`; `@odata.nextLink` is discarded. A workbook or folder on a later page cannot be selected from that listing. Microsoft documents this pagination in [List children of a driveItem](https://learn.microsoft.com/en-us/graph/api/driveitem-list-children?view=graph-rest-1.0).

Implement a bounded next-page / “load more” path for folder listings and search results. Validate continuation URLs against the fixed Graph origin before sending credentials; never accept an arbitrary client URL. Do not recursively crawl the whole drive. Add a focused test where the workbook appears on the second page and remains selectable. Preserve server-side time and response limits.

### The release sequence cannot perform OAuth under a write freeze

The report says to promote, verify real-domain OAuth, and only then unfreeze. But Microsoft connection creates and consumes `excel_autorizacion` rows and stores credentials; employee login also writes. These actions cannot succeed under the proposed database freeze. Also, `test_congelar_postgres.py` loads the current adapter twice; it does not prove the actual schema-7 deployment's response behavior.

Use this sequence:

- Complete real Microsoft and functional acceptance on isolated Preview before production work.
- Rehearse the actual old-code/new-code migration and freeze against an isolated restored backup. It is enough that old writes are blocked; do not promise the old code displays a new maintenance message it does not contain.
- In the agreed production window, freeze writes, confirm active transactions are stopped, and take the final private backup. Migrate/provision using the deliberate operator-only write override.
- Stage the reviewed build without promoting its public domain; perform checks compatible with the freeze. Prepare a valid test session through the controlled provisioning step if necessary. Do not run synthetic import/destructive smoke tests against production data.
- Promote, verify read-only continuity, then reopen writes. Perform real-domain login/OAuth/Refresh acceptance immediately afterward. Explicitly record that these are post-unfreeze checks.
- If post-unfreeze acceptance fails, freeze again before deciding recovery; do not blindly restore over new writes. For rollback to a restored database, verify the old-code deployment actually uses that restored target. Re-promoting an old Vercel deployment does not by itself update its captured database configuration.

## Developer work that can proceed now

1. Incorporate PR #4 into the feature branch, fix pagination, implement the narrow legacy-access manifest, and update the existing rehearsal for schema 7 → 9 and rollback. Reuse the existing tests and scripts. Do not build a new verification framework.
2. Correct the release runbook as above. Explicitly distinguish the authenticated employee workflow from the anonymous legacy view, including exports and private-item denial.
3. Run the relevant new regression tests and the normal CI suite on the integrated candidate. Fix failures; do not repeatedly run unchanged suites or manufacture additional coverage targets. Record exact tested SHA.
4. Prepare a short, executable cloud-operator handoff using the existing scripts: commands, target environment, required nonsecret configuration, and expected outcomes. Keep secret values outside Git and chat. Developer implementation does not need to wait for cloud access.

## Cloud setup and first real trial — run alongside the code work

This needs an authorized operator with Vercel, Neon and Microsoft access. Claude Cloud's network restriction remains a real access boundary. The supervisor reviews and directs; the owner should only perform account-holder actions that cannot be delegated. Identify the operator or the exact missing access action in the next report, rather than leaving “blocked” unassigned.

1. Diagnose Vercel's recorded deployment block. Use the supported account/GitHub linkage or approval flow; do not forge commit authorship. An authorized CLI Preview of the exact candidate is acceptable to unblock connector testing while Git-triggered Preview is repaired. Keep production untouched and Preview database isolation verified.
2. Register/configure the Microsoft app for the owner's organizational account; retain personal-account support if already configured. Use the existing delegated read scopes and exact callback URLs. An app registered elsewhere does not bypass the company tenant's consent policy. If registration or consent is denied, return the precise Microsoft error and the specific account-holder/admin action needed.
3. Configure Preview-only Microsoft credentials and encryption key, enable pgcrypto on the isolated Neon Preview database, migrate it, and deploy the integrated candidate. Use the actual configured runtime limit. Never set shared Production/Preview database or connector secrets.
4. First prove login and workbook selection through the owner's work account. Confirm worksheet, stable unique ID and currency mapping. Read the supplied real workbook without editing it. Use a small test workbook in the same business account for deliberate mutations, so test steps do not damage business data. Keep any real data loaded into Preview private and out of logs/reports.
5. Run one focused hosted acceptance sequence: connect/import; second employee saves an addition, an edit and a deletion in the test workbook; Refresh shows the expected changes; repeat Refresh creates no duplicate; invalid/duplicate-ID data leaves the prior version active; saved maps stay unchanged; reconnect recovers revoked access. Verify persistence from a separate browser/device with the owner's Mac off, after the initial grant. Record timings and the candidate/deployment identity.
6. Use Neon Preview/its disposable test database to verify schema and pgcrypto compatibility with PostgreSQL 18. Do not run a suite that assumes disposable data against production or a Preview database containing the real workbook.

Keep most edge-case/security regressions in the existing local fixture suite. Do not manually repeat every fake-Microsoft scenario on the real account. A real hosted failure warrants a targeted fix and regression; it does not automatically warrant redesign.

## Production completion gate

After the Preview trial passes, finish one private real-backup migration/rollback rehearsal, verify the legacy access manifest, provision the actual employee accounts through the existing mechanism, and agree the release window. Return the integrated candidate, CI status, Preview URL/deployment ID, business-account acceptance results and rehearsal result for supervisory release review. This document does not authorize replacing production.

The app is done before BigQuery only after production has been released and the owner/employee can connect the workbook, refresh saved cloud changes, reopen maps/export, and retain data with the Mac off. A green local suite or a working Preview is a milestone, not that completion claim.

Next report: one concise table of completed / remaining / access-blocked items, the exact instruction and implementation SHAs, and the next operator action. Do not ask again about the four decisions resolved above. Update the PR description to match the full current scope.

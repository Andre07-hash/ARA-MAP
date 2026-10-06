# Supervisor review of developer readiness evidence

Reviewed the remote branch `claude/trusting-ptolemy-h3ondg` at `a834a247e9a6d1372e7631592174fe9fb738806c`. This review read the report, result JSON, rehearsal script and relevant source diff; it did not independently rerun the full rehearsal or certify unfinished Stage 2 work.

## Accepted evidence and remaining gates

- PR #1 is a scoped CI/documentation/deployment-gate change and has recorded passing GitHub checks. It remains open and unmerged at this review.
- The fictional-data local rehearsal records 26 PASS / 1 FAIL. It demonstrates preserved legacy data, idempotent migration, fictional account provisioning and backup recovery on disposable local Postgres. Accept this as useful local evidence, not a Vercel deployment or a real-production-data rehearsal.
- The FAIL is the anonymous login error response exposing database details. Extract the narrow generic-response correction already present on the developer's Stage 2 branch, with local and cloud-adapter HTTP regression tests. Do not merge the whole unfinished Stage 2 branch to obtain this fix.
- The new branch tests cover the demonstrated unexpected exception inside the endpoint dispatch boundary. They do not claim to audit every possible logging/error path in the application.
- Step 3 remains partially complete: a hosted preview, real-data copy rehearsal and operational rollback validation are still outstanding. Reporting (step 5) is complete as a status report, not release acceptance.

## Access checked in this supervisor session

- Vercel CLI authentication works. A fresh project read confirms the existing `ara-map` project still has no Git link and still targets production deployment `dpl_3vsdvzhV86Y1goinejgcHP83vNML`. The developer container's Vercel network restriction is not a restriction of this session.
- Neon profile inventory reports DEFAULT with no account and missing credential file. No `NEON_API_KEY` is configured in this process. There is no authenticated Neon management connection available here to create a preview branch. The existing production SQL connection does not establish authorization/access to Neon's project-management API.
- The owner chose **IT will provide the Preview database**. Wait for an explicitly isolated test destination supplied securely; do not request Neon login again or provision a replacement/claimable account. IT should provide a pooled application connection and direct migration connection, destination identity and test-only scope. No token or connection string should be pasted into chat or committed.
- No Vercel environment, Git integration, production deployment or production data was changed during this follow-up. There is still no preview URL.

## Next sequence

1. Review/merge PR #1 before connecting GitHub, so the production branch carries the deployment guard. Keep the Stage 2 branch preserved; its current tree lacks that guard.
2. Review the separate generic-error correction. Once PR #1 is merged, retarget/rebase this narrow follow-up onto `main`; reconcile the same fix when Stage 2 is resumed. Do not require Stage 2 completion now.
3. With authenticated Neon access or an IT-provided test target, establish a dedicated disposable Preview database and fictional accounts. Verify effective environment values without printing secrets and preserve Production values. Only then connect GitHub and enable feature-branch previews while keeping `main` disabled.
4. Deploy the exact reviewed candidate as Preview; verify hosting, dependencies, authentication, map/import/export flows and commit traceability. This is the remaining infrastructure milestone before the Excel/BigQuery build.
5. Leave the existing public production site serving its current deployment while development continues. Production replacement still needs explicit public-access continuity, a tested real-data migration and actual team-account provisioning. Do not auto-publish or anonymize access to legacy data as an improvised workaround.

## Rehearsal-script limitation to fix before real-data rehearsal

The current `rehearse.py` accepts a commit, loopback admin URL, Python executable and output directory; it creates new databases and seeds fictional schema-7 data. It has no option to accept an existing production backup. Passing a loopback server with a restored production copy would not by itself test that copy: the script creates its own databases.

For the real-data gate, add an explicit backup-input mode that restores a supplied backup into a new isolated database, omits fictional seeding and derives expected counts/digests from that restore. Keep the loopback/test-destination checks and preserve the original backup. Real backup contents, credentials and raw business data must remain outside GitHub evidence; commit only sanitized results/digests needed for review.

Restoring database state can discard legitimate writes made after a backup. Any production rollback plan must address a maintenance/read-only window or recovery of intervening writes, and must match code and schema. Do not actually roll the live service backward merely to demonstrate that the old deployment exists.

Excel + BigQuery remains the next product milestone. Public-catalog expansion, Stage 2 smoke-test completion, new lint/type-check CI gates and other improvements remain separate from these immediate readiness fixes.

## Focused validation

`python -m unittest tests.test_server tests.test_cloud` passed all **35 tests**, including the two new anonymous-error regression checks. Tests used disposable local data with cloud adapter behavior exercised over HTTP. GitHub CI supplies the full disposable-Postgres check separately.

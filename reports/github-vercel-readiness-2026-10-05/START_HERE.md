# Priority 0 — GitHub and Vercel readiness

October 5, 2026. The owner moved development to GitHub and requested that required deployment/process changes precede Excel + BigQuery. This packet now comes first. It is not authorization to overwrite production data or publish the unfinished inventory application.

## Verified findings

- Private repository: https://github.com/Andre07-hash/ARA-MAP. GitHub `main`, local HEAD and the remote branch were all `20234c1568614d65da3ce9cc737c5c51cea73bca` at inspection. The latest local Excel/BigQuery plans were not committed in that revision.
- GitHub Actions is enabled, but no workflow, check run or commit status existed. `main` was unprotected. Both ruleset and branch-protection API requests returned HTTP 403 stating that private-repository enforcement requires GitHub Pro (or making the repository public). Keep this repository private; no plan change or purchase was made.
- Existing Vercel project `ara-map`, ID `prj_M8FX8MdxYKNC5GcQ3aB9B8DzPkjZ`, team `team_vC0USUFYDJBbhvdlxoCvd79V`, has no Git repository link. Retain this project and its domain; do not create a replacement simply to connect GitHub.
- Its production target is READY deployment `dpl_3vsdvzhV86Y1goinejgcHP83vNML`, created October 1 via CLI, with no Git source metadata. GitHub push currently does not update it.
- Live `/api/config` returned HTTP 200 and the old shared-password-era configuration. `/api/session`, present in the repository's individual-account implementation, returned 404 on the live service. Source and production are demonstrably different; no authenticated production write was made.
- Vercel lists one `DATABASE_URL` entry targeted at Production, Preview and Development, along with other similarly shared Postgres variables. No branch-specific isolation was shown in that inventory. Do not deploy a preview until its database destination is independently verified to be disposable/separate. Environment values were not printed or decrypted for this audit.
- The current source requires schema 8 and individual team accounts. The actual cloud schema/account readiness was not inspected. A Git connection alone does not migrate data or provision accounts.
- Git ignores `.env*`, `.cloud-access.txt`, `.vercel/` and `datos/`. Real workbook `Base Terrenos 09.26 copy.xlsx` is already tracked in the private repository, alongside fixtures/reports. `.vercelignore` excludes XLSX/reports/tests from deployment, not from GitHub history. Keep access private and review future business-data commits; do not rewrite history or delete originals casually.

The connected Vercel app was unavailable, but the existing authenticated Vercel CLI successfully supplied live read-only project/deployment/environment metadata. GitHub was inspected through authenticated `gh`, not the public web page.

## Changes in this readiness branch

1. `.github/workflows/checks.yml` adds Python tests with an isolated Postgres service plus JavaScript tests on pull requests/main. It uses read-only repository permissions, pinned action revisions, no deployment credentials and no production database. No deploy job is included.
2. `vercel.json` sets `git.deploymentEnabled: false` temporarily. This avoids accidental Git-triggered rollout if the repository is connected before migration and preview isolation are ready. It does not stop explicit CLI deployment and does not alter the currently running deployment.
3. README and handoff entry points put this prerequisite before Excel + BigQuery and remove the casual direct-production deployment instruction. Current local handoff documents are included for developer review through GitHub.

Check `VALIDATION.md` for actual test results and unresolved failures. A configured workflow is not proof that CI passed.

## Developer work, in order

### 1. Establish the repository baseline

Use branches and PRs against `main`; preserve all current work. Run the new checks and resolve failures before calling the baseline green. Fresh clones must run without the author's `.venv-dev`, `.env.local`, local database or unpublished files. Keep dependency installation reproducible enough to explain the tested versions; the bundled openpyxl remains part of the existing local-app contract.

Do not claim branch protection exists: GitHub rejected it under the current private-repository plan. Until the owner chooses a plan with enforcement, use manual PR review and keep automatic production deployment off. Upgrading is optional and is a separate owner decision; never make company code/data public to unlock a feature.

### 2. Separate Preview from Production

On the existing Vercel project, configure a dedicated disposable Preview database and fictional accounts compatible with schema 8. Verify every effective database variable/branch override, not only `DATABASE_URL`, and ensure migrations/setup cannot resolve production by default. Do not change the production connection as a side effect. Future BigQuery and drive credentials must likewise separate test and production resources.

Create a preview environment only with an identified authorized test destination. Do not assume the existence of the Neon integration proves branch isolation. If a new service or paid database is needed, present that concrete requirement before provisioning. Secrets remain in Vercel/company secret configuration, never GitHub source or PR text.

### 3. Rehearse startup and schema/account transition

Fresh-clone the candidate and deploy an explicitly isolated preview from the exact reviewed commit. Preserve `framework: null`, repository-root context, `web/` output and `api/index.py` routing; there is no evidence these need a framework/root rewrite. Verify Python dependency installation, API imports, static assets, sign-in and representative map/import flows.

The old production shared-password variable does not provision the new individual accounts. Use existing schema/account tooling on the test destination and rehearse old-to-new migration on a copy before recommending production cutover. Assess the currently empty public-catalog routes explicitly: new inventory code must not replace the working public site without a reviewed continuity decision. Resolving baseline startup/continuity is Priority 0; do not build deferred catalog enhancements as a shortcut.

Record the current production schema read-only when appropriate access is available. Do not run the default `migrate_cloud.py`/`setup_cloud.py` as a diagnostic: they may use production configuration and mutate data.

### 4. Connect GitHub after the preceding prerequisites

Connect `Andre07-hash/ARA-MAP` to the existing `ara-map` project through Vercel Git settings or supported CLI, using the GitHub App's repository access. Keep production Git deployment disabled initially. Once Preview isolation and the fresh-clone deployment are verified, change the Git configuration through a PR to permit feature-branch previews while keeping `main` disabled. Vercel defaults unspecified branches to enabled; use an exact `main: false` rule without a competing wildcard-true rule.

Verify a feature-branch push creates a Preview deployment attached to the correct SHA and isolated data. Do not add a second GitHub Actions deployment pipeline alongside native Vercel Git integration. CI tests and Vercel previews serve different purposes; a passing Vercel build does not prove tests passed.

### 5. Establish the release procedure

Release from a clean, reviewed commit only. Require green repository checks, verified preview, migration/account rehearsal, backups and rollback instructions. Keep releases deliberate while branch protection is unavailable. If later enabling automatic production deployment, first establish an enforceable review/test gate and confirm production-branch configuration.

A test-preview artifact may contain Preview environment bindings. Do not promote it to production merely because it was tested: build/verify a production-target artifact with the correct production configuration and control when production domains switch. Record commit SHA, deployment ID and environment separately. Production data migrations are an explicit release step, not an automatic side effect of build or every request.

After this prerequisite is demonstrated, resume [Excel + BigQuery](../excel-bigquery-developer-handoff-2026-10-05/START_HERE.md). Existing production remains in place during readiness work.

## Exit evidence

- GitHub contains current instructions and reproducible green test checks.
- Fresh clone builds and runs on Vercel Preview using verified isolated data and test accounts.
- Vercel project links to the intended private repository; a test branch produces a deployment traceable to its SHA.
- Production remains unchanged until the reviewed release; code/schema/account differences have a tested transition or explicit continuity decision.
- Branch-protection limitations, current operational storage, credential scopes and release/rollback ownership are stated accurately.

## Sources

- [GitHub repository](https://github.com/Andre07-hash/ARA-MAP)
- [Vercel GitHub integration](https://vercel.com/docs/git/vercel-for-github)
- [Vercel branch deployment configuration](https://vercel.com/docs/project-configuration/git-configuration#gitdeploymentenabled)
- [GitHub Python CI guidance](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)

# Readiness rehearsal and PR #1 review — October 6, 2026

Scope: steps 1–5 of the owner's readiness request, done from a Claude Code cloud
container. **Nothing was deployed, no Vercel or production setting was changed,
and production data was not read or written.** Everything below ran on a
disposable loopback Postgres 16 cluster with fictional data and fictional
accounts.

## Status at a glance

| Step | Status |
|---|---|
| 1. Review PR #1 | **Done.** Safe to merge as is (checks, docs and a protective `vercel.json` gate; no application change). Findings below. |
| 2. Isolated Preview database + fictional accounts on Vercel | **Blocked.** This container cannot reach `api.vercel.com` (network policy denies it) and holds no Vercel or Neon credential. The tooling and the exact commands are ready (below). |
| 3. Fresh-checkout deployment, migration/recovery rehearsal | **Rehearsed locally: 26 PASS, 1 FAIL (a real finding).** A Vercel-hosted preview build was not possible here. |
| 4. Connect Vercel to GitHub, verify branch previews | **Blocked** (same reason as step 2). This requires the Vercel dashboard or an authenticated CLI. |
| 5. Report | This document. |

## Tested commit

- PR #1 head: `da5a1aa9ced57944f368336d48a1697d5054d84b` (`codex/github-deployment-readiness`), base `main` `20234c1`.
- GitHub Actions on that head ([run 37394433894](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37394433894)): *Python and disposable Postgres* **success** and *JavaScript* **success**. The PR text reports 670 Python and 98 JavaScript tests.
- Comparison candidate: the Stage 2 branch `claude/trusting-ptolemy-h3ondg` at `d2967f1`. It has not been reviewed or merged.

## Fresh-checkout and migration rehearsal (`rehearsal/rehearse.py`)

Evidence: `rehearsal/run-pr1-da5a1aa/results.json` (and `run-stage2-d2967f1/`). It also holds the legacy digests before and after, the pre-migration `pg_dump`, and the adapter logs. Reproduce with:

```sh
python3 reports/github-vercel-readiness-2026-10-05/rehearsal/rehearse.py \
  --commit <sha> --pg-admin-url postgresql://<role>@127.0.0.1:<port>/postgres \
  --python312 <python3.12> --out <new dir>
```

The script refuses any non-loopback database. It never reads `.env*` and never runs `migrate_cloud.py` or `setup_cloud.py`.

**What it does and what happened on `da5a1aa`:**

1. **Fresh clone.** It cloned from GitHub at the exact SHA. The checkout has no `.venv-dev`, `.env.local`, `datos/` or `api/data/`. PASS
2. **Vercel-like bundle.** It took the tracked files and removed everything `.vercelignore` excludes: 138 of 900 files remain. `reports/`, `tests/`, every `.xlsx` and the root `vendor/` are excluded, while `web/` and `api/` are kept. Every asset referenced by `web/index.html` is present. `vercel.json` keeps `framework: null`, `outputDirectory: web`, the `/api/:path* → /api/index.py` rewrite and `git.deploymentEnabled: false`. PASS
3. **Clean runtime.** A Python 3.12 runtime (matching `.python-version`) was built from `pyproject.toml` dependencies only: openpyxl 3.1.5 and psycopg 3.3.6. **openpyxl loads from site-packages, not the excluded vendor copy**, so the deployment does not depend on `vendor/`. PASS
4. **Production-shaped schema-7 workspace.** The frozen pre-change code built a workspace with 3 bases, 104 terrains (40/36/28) and 2 saved maps: one simple, one comparison. It contains mixed USD/MXN/unknown currency, invalid coordinates, HTML-like and formula-like names, and private extras. This is fictional data shaped like production's counts, **not a copy of production**. PASS
5. **Pre-migration backup.** A `pg_dump -Fc` was taken (42 KB). PASS
6. **Candidate against schema 7 before migrating.**
   - `/api/config` and the public list answer, and login returns 500. This is expected: schema 8 tables are missing. PASS
   - **FAIL (real finding F-1).** The 500 response body contains the raw database error text: `relation "team_login_failure" does not exist`. Details in F-1 below.
7. **Migration.**
   - `scripts/esquema.py --url-env …` reported 7 under `--check` (exit 1).
   - The upgrade ran twice (idempotent), and `--check` then exits 0.
   - It refuses a target variable that is not set. PASS
8. **Data preserved.**
   - **Every legacy table is byte-identical** after the migration: base 3, terreno 104, mapa 2, mapa_capa 3, mapa_terreno 116.
   - The in-database `workspace_backup` taken before the upgrade holds the 104 terrains, 3 bases and 2 maps.
   - The schema 8 tables exist. PASS
9. **Accounts.** Two fictional accounts were created with `scripts/cuentas.py --url-env … --password-stdin`. PASS
10. **The bundle's `api/index.py`**, run through a stdlib HTTP server on the migrated database:
    - anonymous `/api/session` and `/api/config` answer;
    - sign-in sets a `Secure; HttpOnly; SameSite=Strict` cookie;
    - signed in, the 3 bases show 40, 36 and 28 terrains;
    - **both saved maps reopen** with their frozen 40 and 76 terrains;
    - an `.xlsx` import through openpyxl works (79 terrains), and the comparison export returns an `.xlsx`;
    - a new inventory draft saves. PASS
11. **Recovery.**
    - Restoring the pre-migration dump into a new database gives schema 7, byte-identical legacy tables and no schema-8 tables. PASS
    - **The pre-change (schema 7) code reads the restored workspace** (3 bases, 2 maps). This is the rollback path: restore the dump, then put the October 1 deployment back. PASS

**Not covered by this rehearsal:**
- Vercel's real build and function runtime, Neon, HTTPS and real domains.
- The actual production rows. The migration was proven on a production-shaped copy, not on a copy of production. Before cutover, an authorized person must take a real `pg_dump` of production and rerun this script against a restored copy of that dump.
- Promoting the old deployment `dpl_3vsdvzhV86Y1goinejgcHP83vNML` again, which needs Vercel access.

## PR #1 review

**Verdict: mergeable.** It changes no application behaviour, and it gates Git-triggered deployments. The workflow is sound:
- read-only permissions;
- pinned actions with `persist-credentials: false`;
- the job-local Postgres container is the only database, and deployment variables are blanked;
- no deploy job.

**Findings** (none of them blocks merging the PR itself):

- **F-1 (from `main`, not introduced by the PR; LOW, security hygiene).**
  - *Problem:* unexpected errors return `Error inesperado: <exception text>`. Against an unmigrated or broken database this exposes table names and SQL to anonymous callers. The rehearsal reproduced it on `/api/login`.
  - *Status:* fixed on the Stage 2 branch (O-5). The same rehearsal on `d2967f1` returns `{"error":"Ocurrió un error inesperado…","detalle":{"code":"internal"}}` with no internals.
- **F-2 (continuity — blocks production cutover).**
  - *Problem:* on `main`, anonymous visitors can no longer see the 104 legacy terrains: bases and maps return 401, and the new public catalog is empty (`total: 0`).
  - *Why:* today's production lets visitors browse without signing in, so cutting over `main` removes the public site.
  - *What the Stage 2 branch adds:* real publication and the public catalog. Even so, records only appear after someone publishes inventory records, and the legacy bases are not inventory records. Adopting them is the deferred Stage 3 import.
  - *Decision needed before cutover:* do visitors keep public access to the legacy terrains, and how?
- **F-3 (operations).** Production has no `team_user` table. After migration nobody can sign in until accounts are created with `scripts/cuentas.py --url-env <production variable>`. Plan that as an explicit cutover step, with each person entering their own password.
- **F-4 (minor, CI).**
  - CI does not run `ruff`/`mypy` (which `verificar.sh` does), and tests only Python 3.12. The local app also promises macOS's Python 3.9, which `test_packaging` partly covers.
  - Consider adding lint and type checks later. Not needed for this PR.
- **F-5 (follow-up).** `git.deploymentEnabled: false` also blocks previews. When step 4 is done, change it in a reviewed PR to `{"main": false}` with no wildcard `true`, so feature branches preview and `main` does not.
- **F-6 (sequencing).** The Stage 2 branch was cut from `main` and lacks this PR's `vercel.json` gate; the rehearsal flagged it. Merge PR #1 first, then rebase or merge Stage 2 onto it.

## What the owner needs to do (blocked steps 2 and 4)

1. **Preview database.**
   - Create a separate disposable Postgres for Preview, such as a new Neon branch or database that is not a copy of production.
   - In Vercel → `ara-map` → Settings → Environment Variables, give `DATABASE_URL` (and every other Postgres variable the Neon integration created) a **Preview-only** value that points at it.
   - Leave the Production values untouched, and confirm that no shared all-environments entry still applies.
2. **Prepare the preview database.** With an explicit variable pointing at the preview database only, run:
   - `scripts/esquema.py --url-env PREVIEW_DATABASE_URL`
   - `scripts/cuentas.py --url-env PREVIEW_DATABASE_URL --password-stdin crear <fictional user> "<Name>"`
3. **Connect GitHub.**
   - In Vercel → `ara-map` → Settings → Git, connect `Andre07-hash/ARA-MAP`, keeping the existing project and domain.
   - Then merge a PR changing `vercel.json` to `{"git": {"deploymentEnabled": {"main": false}}}`.
   - Push a test branch and confirm that its Preview URL shows that branch's SHA and the preview database.
4. **Let a session do this for you.** To have a future session do steps 1–3 itself:
   - allow `api.vercel.com` (and `console.neon.tech` if Neon is used) in this environment's network settings;
   - store a Vercel token scoped to the team as the environment variable `VERCEL_TOKEN`, and a Neon API key as `NEON_API_KEY` if needed.

   Never paste tokens into chat.

## Excel + BigQuery

Not started. It is gated behind verified readiness, which is still blocked, and it needs the company inputs in `excel-bigquery-developer-handoff-2026-10-05/COMPANY_SETUP.md`:
- the drive service and workbook;
- a stable row ID;
- the GCP project, dataset and region, plus a separate test dataset;
- the service identity.

None of these is available yet. This container does have `gcloud` and `bq` configured with an access token. Whether that token belongs to the company project, and what it is scoped to, has not been checked and must not be assumed.

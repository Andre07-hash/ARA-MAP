# Preview setup runbook — for the supervisor's Mac session

October 6, 2026. The developer container cannot reach Vercel or Neon (its network policy denies `api.vercel.com` and `console.neon.tech`) and holds no credentials for them. These steps are for the authenticated Mac session.

**Ground rules:**
- Never paste a token, password or connection string into chat, a PR or a commit.
- `.env*` files are ignored by Git, and the checker prints none of their values.
- Production keeps its current deployment and its current variables throughout.

**Tools on this branch** (all in `reports/github-vercel-readiness-2026-10-05/`):

| Tool | What it does |
|---|---|
| `preview/check_preview_env.py` | Proves that no *effective* Preview database variable reaches Production. It never prints secrets. |
| `preview/preview_smoke.py` | Tests a real Preview URL: build identity, sign-in, map data, import, export and persistence. It refuses the production alias. |
| `rehearsal/rehearse.py --backup … --private-dir …` | The real-data migration and recovery gate (section H). |

**Variables to know:**
- **Neon project:** `ara-map-db`, id `tiny-salad-83614342`.
- **Vercel project:** `ara-map`, `prj_M8FX8MdxYKNC5GcQ3aB9B8DzPkjZ`.
- **Production deployment, which must not change:** `dpl_3vsdvzhV86Y1goinejgcHP83vNML`.
- **The effective application variable:** `api/index.py` copies `DATABASE_URL` into `ARA_MAP_DATABASE_URL` *only if the latter is unset*.
  - If `ARA_MAP_DATABASE_URL` exists for Preview, it wins silently.
  - The checker fails in that case.

## A. Choose the commit

1. Merge PR #2, the generic-error fix, so that the Preview build does not leak database errors.
2. The reviewed commit is then `main`'s HEAD:
   ```sh
   git fetch origin && git rev-parse origin/main
   ```
   Record it as `$SHA`.

## B. Neon: a Preview branch with no production data

A normal Neon branch is a full copy of its parent's data, and roles created through Neon are members of `neon_superuser`. **A plain branch of production would therefore put production data inside Preview.** Use a schema-only branch. Inside it, use a database and role that exist only there.

```sh
P=tiny-salad-83614342
neonctl branches list --project-id $P                     # note the production (default) branch
neonctl branches create --help | grep -i schema           # confirm --schema-only is supported
neonctl branches create --project-id $P --name preview-ficticio --schema-only
neonctl roles create     --project-id $P --branch preview-ficticio --name ara_preview
neonctl databases create --project-id $P --branch preview-ficticio --name ara_preview --owner-name ara_preview
```

**Check before going on.** In the new branch, the inherited database must show **0 rows** in `base`, `terreno` and `mapa`. Check it with `psql` on that branch's connection string.

**If any rows exist, stop.**
1. Delete the branch: `neonctl branches delete preview-ficticio --project-id $P`.
2. Report it, because that branch held a copy of production.
3. The fallback is a separate Neon project, `ara-map-preview`, under the same account. Check the plan or cost before creating it.

**Connection strings.** Pipe them straight into the next commands; don't display them.
- **Pooled, for the app:**
  ```sh
  neonctl connection-string preview-ficticio --project-id $P --role-name ara_preview --database-name ara_preview --pooled
  ```
- **Direct, for migrations:** the same command without `--pooled`.

Record the **database identity** for the report:
- project `tiny-salad-83614342`;
- branch `preview-ficticio` and its branch id from `neonctl branches get`;
- its endpoint id (`ep-…`);
- database `ara_preview`, role `ara_preview`.

## C. Vercel: split Preview from Production

1. Link a clean checkout to the existing project, then list the variables and their targets:
   ```sh
   vercel link --project ara-map --yes
   vercel env ls
   ```
2. **Turn off per-preview Neon branching.** In Vercel → `ara-map` → Integrations → Neon, make sure "create a branch for each preview deployment" is **off**. It would branch production data for every preview.
3. **Take Preview off every shared database variable.**
   - The variables: `DATABASE_URL`, `DATABASE_URL_UNPOOLED`, `POSTGRES_*`, `PG*`, `NEON_*` and `ARA_MAP_DATABASE_URL`.
   - Use the dashboard, not CLI `rm`: Settings → Environment Variables → edit each one, untick **Preview** (and **Development**), keep **Production** ticked and **leave the value unchanged**, then save.
4. **Add Preview-only values:**
   ```sh
   neonctl connection-string preview-ficticio --project-id $P --role-name ara_preview --database-name ara_preview --pooled \
     | vercel env add DATABASE_URL preview
   neonctl connection-string preview-ficticio --project-id $P --role-name ara_preview --database-name ara_preview \
     | vercel env add DATABASE_URL_UNPOOLED preview
   ```
   - Do **not** add `ARA_MAP_DATABASE_URL` to Preview.
   - Make sure `OPENAI_API_KEY`, `ARA_MAP_IA_CLAVE` and `ARA_MAP_IA_PROVEEDOR` do not target Preview.
5. **Verify** (expected: `PASS`, schema none, 0 rows):
   ```sh
   vercel env pull --environment=preview    .env.preview.check
   vercel env pull --environment=production .env.production.check
   python3 reports/github-vercel-readiness-2026-10-05/preview/check_preview_env.py \
       .env.preview.check .env.production.check --connect
   ```
   Keep the printed table (endpoints and database names only) for the report.

## D. Schema 8 and fictional accounts, explicitly targeted

```sh
export PREVIEW_MIGRATION_URL="$(neonctl connection-string preview-ficticio --project-id $P --role-name ara_preview --database-name ara_preview)"
python3 scripts/esquema.py --url-env PREVIEW_MIGRATION_URL
python3 scripts/esquema.py --url-env PREVIEW_MIGRATION_URL --check            # exit 0, "versión 8"
python3 scripts/cuentas.py --url-env PREVIEW_MIGRATION_URL crear ensayo.preview "Ensayo Preview"   # password prompted twice
python3 scripts/cuentas.py --url-env PREVIEW_MIGRATION_URL listar
unset PREVIEW_MIGRATION_URL
```

- Do not run `migrate_cloud.py` or `setup_cloud.py`: without arguments they target production.
- Rerun the checker with `--connect`. It should show schema 8, one or more `team_user` rows and 0 `base` rows.
- Then delete the `.env.*.check` files.

## E. Deploy the reviewed commit as a Preview (CLI, before Git is connected)

```sh
git clone https://github.com/Andre07-hash/ARA-MAP.git ara-preview && cd ara-preview && git checkout $SHA
vercel link --project ara-map --yes
vercel deploy                      # never --prod; prints the Preview URL
vercel inspect <preview-url>       # record the deployment id (dpl_…) and target "preview"
```

If Deployment Protection is on, create a "Protection Bypass for Automation" secret under Project → Settings → Deployment Protection. Export it only in your shell.

## F. Verify the hosted Preview

```sh
export ARA_PREVIEW_PASSWORD=…                 # the fictional account's password, typed here, not stored
export VERCEL_AUTOMATION_BYPASS_SECRET=…      # only if protection is on
python3 reports/github-vercel-readiness-2026-10-05/preview/preview_smoke.py \
    --url <preview-url> --commit $SHA --user ensayo.preview \
    --out reports/github-vercel-readiness-2026-10-05/preview/run-${SHA:0:7}
```

**What the smoke test checks:**
- Served by Vercel, with static files byte-identical to `$SHA`.
- The anonymous policy, and sign-in with a `Secure` cookie.
- An `.xlsx` import, with openpyxl coming from the dependencies.
- Map data, a saved map and an `.xlsx` export.
- Persistence across a second session, and logout revocation.

**Then check in a browser:**
1. Sign in.
2. Open the imported base on the map and in the table, select a terrain, and export.
3. Reload the page and confirm the session and the data are still there.

**Confirm production is untouched.** Run `vercel inspect ara-map-ivory.vercel.app`; it must still show `dpl_3vsdvzhV86Y1goinejgcHP83vNML`.

Commit `preview/run-<sha7>/results.json`. It holds statuses, counts and hashes only.

## G. Connect GitHub, then enable feature-branch previews

1. Connect the repository: Vercel → `ara-map` → Settings → Git → connect `Andre07-hash/ARA-MAP`, production branch `main`.
   - `main` still has `git.deploymentEnabled: false`, so nothing deploys automatically.
   - Keep the existing project and domain.
2. Tell the developer that isolation (C/D) and the CLI Preview (E/F) passed. The developer then opens a PR whose only change is:
   ```json
   "git": { "deploymentEnabled": { "main": false } }
   ```
   It has no wildcard `true` rule.
   - Vercel reads `vercel.json` from the pushed commit.
   - That PR's own branch push should therefore create a Preview deployment linked to its commit.
3. Verify that Preview:
   - The Vercel dashboard shows the PR branch and the commit SHA.
   - The Preview uses `ara_preview`; rerun `preview_smoke.py --commit <that sha>`.
   - `vercel ls --prod` shows no new production deployment.
4. Merge only after review.
   - From then on, feature branches get previews.
   - `main` never deploys automatically: a production release stays an explicit `vercel deploy --prod` from a reviewed commit, after the gates in H.

## H. Before any production replacement (not part of this milestone)

1. **Public-access continuity decision.** Today anonymous visitors browse the legacy terrains; `main` makes them private.
2. **Real employee accounts.** Each person enters their own password through `scripts/cuentas.py` against production, as an explicit release step.
3. **Real-data rehearsal.**
   ```sh
   pg_dump -Fc "$PRODUCTION_URL" -f ~/ara-backups/prod-YYYYMMDD.dump
   ```
   - Use a read-only role if one exists, and keep the dump outside every Git folder.
   - Then run on a disposable local Postgres:
     ```sh
     python3 reports/github-vercel-readiness-2026-10-05/rehearsal/rehearse.py --commit <release sha> \
         --pg-admin-url postgresql://<role>@127.0.0.1:<port>/postgres --python312 <python3.12> \
         --backup ~/ara-backups/prod-YYYYMMDD.dump --private-dir ~/ara-backups/rehearsal-YYYYMMDD \
         --out reports/github-vercel-readiness-2026-10-05/rehearsal/run-real-<sha7>
     ```
   - The script refuses a `--private-dir` inside a Git tree.
   - It writes data-bearing files (dumps, adapter logs) only there.
   - `--out` then gets counts, ids and digests only, safe to commit.
4. **Rollback plan.** A maintenance or read-only window covering the migration, plus the restore of the pre-migration dump. Restoring discards writes made after the backup. Then re-promote `dpl_3vsdvzhV86Y1goinejgcHP83vNML`. Do not roll the live site back merely as a demonstration.

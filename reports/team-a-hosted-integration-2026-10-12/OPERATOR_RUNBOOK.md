# Private pilot — operator runbook (future steps, nothing here has been run)

For whoever holds the Vercel, Neon and AWS access. Written for contract
`reports/hosted-transfer-contract-2026-10-12/START_HERE.md` on
`codex/supervisor-completion-brief`. **Every step below is held until the
owner releases provisioning and deployment.** No step was executed to write
this file, and no identifier in it is real: `<…>` marks a value the operator
supplies.

Ground rules, unchanged from the 5 October Preview runbook:

- Never paste a password, token, connection string or role credential into a
  chat, a commit, a PR or a report. Pipe secrets from one command into the
  next, or type them at a hidden prompt.
- The pilot shares nothing with production: its own database, its own bucket,
  its own role, its own Preview-scoped variables.
- `scripts/setup_cloud.py` and `scripts/migrate_cloud.py` read `.env.local`
  (production) unless given `--url-env`. They are not used here at all.
- Record every identity you create (section 8). A hosted result without the
  exact commit, deployment and target identities is not evidence.

## 0. Before starting

| Need | Why |
|---|---|
| The reviewed commit SHA of the combined candidate | The only thing that gets deployed |
| Vercel access to the project, with OIDC federation available | Deployment, variables, token issuer |
| The Vercel team slug and project name, exactly as Vercel spells them | They are part of the token's issuer, audience and subject |
| Neon access to create a project (or an empty database in one used by nothing else) | Isolated database |
| An AWS account where you may create one bucket, one IAM OIDC provider and one role | Isolated private file store |
| `psql`, `vercel`, `aws` CLIs and Python 3.10+ with `psycopg` on the operator's machine | Commands below |
| Team B's verifier and recovery procedure at the reviewed commit (`scripts/verificar_archivos.py`, B's report) | Section 7 |

## 1. Isolated database

1. Create a **new Neon project** for the pilot. Do not branch the production
   project: an ordinary Neon branch is a full copy of its parent's data.
2. In it, one database and one role used only by the pilot.
3. Confirm it is empty before going on:
   ```sh
   psql "$PILOTO_DB_DIRECTA" -Atc "select count(*) from information_schema.tables where table_schema = 'public'"
   ```
   Expected `0`. `PILOTO_DB_DIRECTA` is the direct (unpooled) connection
   string, exported in this shell only.
4. Create the schema and check it:
   ```sh
   python scripts/esquema.py --url-env PILOTO_DB_DIRECTA
   python scripts/esquema.py --url-env PILOTO_DB_DIRECTA --check
   ```
   The second command exits 0 and reports the version this code expects.

## 2. Isolated private file store

Team B owns the store's exact settings; their report at the reviewed commit is
authoritative for lifecycle rules and the role's action list. The shape:

1. One bucket for the pilot, in one region, used by nothing else.
2. Block all public access. Enable versioning. Default encryption on.
   A bucket policy that denies requests without TLS.
3. Lifecycle only for the staging prefix `temporal/`: current objects,
   noncurrent versions and delete markers. **No lifecycle rule on `final/`:**
   every final version is kept for the pilot.
4. An IAM OIDC identity provider for the Vercel **team issuer**:
   - provider URL `https://oidc.vercel.com/<TEAM_SLUG>`
   - audience `https://vercel.com/<TEAM_SLUG>`
5. One role for the pilot whose trust policy allows
   `sts:AssumeRoleWithWebIdentity` from that provider with **exact** matches:
   - `oidc.vercel.com/<TEAM_SLUG>:aud` = `https://vercel.com/<TEAM_SLUG>`
   - `oidc.vercel.com/<TEAM_SLUG>:sub` =
     `owner:<TEAM_SLUG>:project:<PROJECT_NAME>:environment:preview`

   No wildcard in either condition. A production role, if there is ever one,
   is a different role on a different bucket with `environment:production`.
6. The role's permissions: only this bucket, only the actions B lists.

There are no long-lived access keys anywhere in this design. Do not create any.

## 3. Vercel configuration (Preview scope only)

1. Project Settings → Security → enable **Secure Backend Access with OIDC
   Federation**, issuer mode **Team**.
2. Environment variables, each targeted at **Preview only**:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the pilot's **pooled** connection string |
   | `ARA_MAP_ARCHIVOS_S3_BUCKET` | the pilot bucket's name |
   | `ARA_MAP_ARCHIVOS_S3_REGION` | its region |
   | `ARA_MAP_ARCHIVOS_S3_ROLE_ARN` | the pilot role's ARN |

   ```sh
   vercel env add DATABASE_URL preview        # paste at the hidden prompt, or pipe it in
   ```
3. Must **not** exist for Preview: `ARA_MAP_DATABASE_URL` (it would win over
   `DATABASE_URL` silently), `ARA_MAP_ARCHIVOS_S3_ENDPOINT` (local tests only;
   the cloud entry refuses it), `ARA_MAP_READ_ONLY`, `ARA_MAP_ARCHIVOS`,
   any `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, and the assistant's keys
   (`OPENAI_API_KEY`, `ARA_MAP_IA_*`).
4. No production-scoped database variable may reach Preview, and the Neon
   integration's "create a branch for each preview deployment" stays off.
   The 5 October checker proves the first without printing values:
   `reports/github-vercel-readiness-2026-10-05/preview/check_preview_env.py`.
5. Do not change `vercel.json`, the production deployment or any
   production-scoped variable. Git deployments stay disabled.

What a wrong value looks like from the application: the portal, the table and
the map keep working; only file operations answer
`503 almacen_no_configurado` (a variable is missing or malformed, or the
platform sent no token) or `503 almacen_no_disponible` (the provider refused
or failed). Neither message contains the value.

## 4. Accounts and grants

Accounts exist only through this command. There is no self-service password
change in the pilot; resets are the operator's.

```sh
python scripts/cuentas.py --url-env PILOTO_DB_DIRECTA crear <login> "<Nombre visible>" --rol admin
python scripts/cuentas.py --url-env PILOTO_DB_DIRECTA crear <login> "<Nombre visible>"
python scripts/cuentas.py --url-env PILOTO_DB_DIRECTA listar
python scripts/cuentas.py --url-env PILOTO_DB_DIRECTA restablecer <login>
python scripts/cuentas.py --url-env PILOTO_DB_DIRECTA desactivar <login>
```

- Passwords are typed at a hidden prompt, at least 12 characters, and handed
  to each person outside this repository and outside chat.
- An operator account can see nothing until an administrator grants it a work
  base in the portal (**Bases de trabajo y accesos**).
- Resetting a password, deactivating an account or changing its role ends
  that person's open sessions.

## 5. Preview deployment

From a clean checkout of the reviewed commit, linked to the existing project:

```sh
git status --porcelain            # must print nothing
git rev-parse HEAD                # must equal the reviewed SHA
vercel deploy                     # Preview is the default target; never --prod
```

Record the deployment id and URL. Then confirm in the deployment's own
details, without assuming: the Python version in use (3.12 expected), the
function's maximum duration and memory, and that the build installed the
pinned SDK. These are recorded, not claimed from the repository.

## 6. Hosted proof (the release gate; see the contract for the full list)

Synthetic files and fictional accounts only. Each item is a pass/fail line in
the hosted report with the request count, bytes and elapsed time where it
applies.

1. A valid KMZ above 4.5 MB and one at the 20 MiB limit: upload, explicit
   candidate selection, activation, boundary drawn for a terrain with empty X/Y.
2. An invalid replacement KMZ: the previous boundary is still drawn.
3. A 25 MiB PDF: upload, then download; the downloaded file's SHA-256 equals
   the original's. Record the nine slice requests and their time.
4. A second signed-in session with access reads the same file and boundary.
5. An account without the base is refused the file and the geometry, and gets
   the same answer as for a file that does not exist.
6. Access removed between two download slices: the next slice is refused.
7. A request carrying a made-up `x-vercel-oidc-token` header behaves exactly
   like one without it (the platform's token is the one that arrives).
8. Redeploy the same commit: files, history and boundaries are still there.
9. Restore (section 7) into a fresh target, verified.
10. Peak duration and memory of a 20 MiB KMZ completion and of a 25 MiB slice.

## 7. Backup and restore

**What must come back together:** the database and the bucket, as of one
moment. The database says which final objects exist and what their size and
SHA-256 are; the bucket holds them.

**Prerequisites kept from day one:** Neon point-in-time restore available for
the pilot project; bucket versioning on; no lifecycle on `final/`.

**Restore into a fresh isolated target — never over the running pilot:**

1. Restore the database to the chosen moment as a new Neon branch or project.
2. Restore the bucket's final objects into a **new** bucket following B's
   object-version procedure, choosing for each referenced key the version
   whose size and SHA-256 match the database.
3. A point-in-time restore is not the application's filtered backup: it
   brings back operational rows too. **Before anyone can reach the restored
   target**, clear them:
   ```sql
   BEGIN;
   DELETE FROM team_session;        -- everyone signs in again
   DELETE FROM team_login_failure;  -- no stale lockouts
   DELETE FROM archivo_trabajo;     -- no processing lease survives a restore
   COMMIT;
   ```
   Run it only against the restored target's direct connection string, after
   confirming which database the shell variable points at.
4. Run B's read-only verifier against the restored database and the new
   bucket. Acceptance fails if any referenced final object is missing or its
   size or SHA-256 differs, or if a history, attempt, geometry or active
   boundary link is broken. Unreferenced objects are reported, not deleted.
5. Uploads that were in progress at the restore moment come back as pending
   with their original deadlines and without their staged bytes. They are
   reported, not repaired: the person cancels and starts again, or they
   expire on their own. They never become available files.
6. Only then point a deployment's Preview variables at the restored pair.

## 8. Identities to record for the hosted report

Commit SHA · Vercel project and deployment id/URL · Python version, duration
and memory in force · Neon project, branch, endpoint, database and role names
· bucket name and region · role name (not credentials) · OIDC issuer mode ·
who ran each step and when.

## 9. What is deliberately absent

Production data, production variables, public catalogues, self-service
passwords, automatic orphan cleanup, any deletion from `final/`.

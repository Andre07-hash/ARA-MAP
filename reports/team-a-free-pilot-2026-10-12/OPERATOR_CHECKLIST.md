# Free private pilot — operator checklist (future steps; none has been run)

For whoever will hold the Render, Neon and Supabase accounts. Contract:
`reports/free-private-pilot-2026-10-12/START_HERE.md` on
`codex/supervisor-completion-brief`. **Every step is held until the owner
releases provisioning and deployment.** `<…>` is a value the operator supplies.

## Hard limits of this pilot

- **No payment method anywhere.** Free plans only: no trial that converts, no
  credits, no add-on, no paid disk, no domain. If a provider asks for a card,
  stop and report which screen asked; do not continue on a paid plan.
- **Storage is 1 GB in total.** Working budget: **700 MB for every final file
  and its history.** Record count says nothing about it: 100 terrains with one
  maximum-size KMZ (20 MiB) and one maximum-size PDF (25 MiB) each would need
  about 4.7 GB. **Before any real file is loaded, add up the real files.** If
  they do not fit, that is a blocker to report, not something to trim quietly.
- **The service sleeps** after about 15 idle minutes and takes about a minute
  to wake. The storage project pauses after a week without use. A free
  service can be suspended when its bandwidth runs out. This is a pilot, not
  an always-on commitment.
- **Nothing lives on the host's disk.** Every restart begins from the code.
- Never paste a password, key or connection string into chat, a commit, a PR
  or a report. Secrets are typed into provider dashboards or hidden prompts.

## 0. Before starting

| Need | Why |
|---|---|
| The reviewed commit SHA of the combined candidate | The only thing deployed |
| Free accounts on Render, Neon and Supabase, created without a card | Host, database, file bytes |
| `psql`, `pg_dump`, `pg_restore` no older than the Neon server's major version; Python 3.10+ with `psycopg` | Commands below |
| A private folder outside the repository for backups | Section 7 |
| Team B's verifier/exporter at the reviewed commit | Sections 7 and 8 |

## 1. Database (Neon Free)

1. A **new** Neon project for the pilot. Never a branch of another project: a
   branch is a copy of its parent's data.
2. One database and one role. Note the plan's limits (storage, compute hours)
   as shown in the dashboard on that day.
3. Export the **direct** (unpooled) connection string in this shell only as
   `PILOTO_DB`, then confirm the database is empty, create the schema and
   check it:
   ```sh
   psql "$PILOTO_DB" -Atc "select count(*) from information_schema.tables where table_schema='public'"   # 0
   python scripts/esquema.py --url-env PILOTO_DB
   python scripts/esquema.py --url-env PILOTO_DB --check        # exit 0
   ```
   `scripts/setup_cloud.py` and `scripts/migrate_cloud.py` are not used: they
   read `.env.local` (production) unless told otherwise.

## 2. File store (Supabase Free, Storage only)

1. A **new** Supabase project used only for these files. Its database, Auth
   and API are not used by ARA Map.
2. One **private** bucket. No public bucket, no anonymous read or write
   policy, no public URL.
3. The server-side secret key for that project is the only credential. It
   bypasses the provider's own row policies, so it goes only into the host's
   secret settings — never in the browser, the repository or a log.
4. Record the storage usage shown by the dashboard (it starts near zero).

Team B's report at the reviewed commit is authoritative for anything more
specific about the bucket.

## 3. Host (Render Free)

1. New **Web Service** from the repository at the reviewed commit, using
   `render.yaml`: plan **Free**, auto-deploy **off**, no disk.
2. Secrets, typed in the dashboard:

   | Variable | Value |
   |---|---|
   | `ARA_MAP_DATABASE_URL` | the pilot's **pooled** connection string |
   | `ARA_MAP_HOST_PUBLICO` | the service's hostname only, e.g. `<nombre>.onrender.com` — no `https://`, no path |
   | `ARA_MAP_ARCHIVOS_SUPABASE_URL` | the storage project's URL |
   | `ARA_MAP_ARCHIVOS_SUPABASE_KEY` | its server-side secret key |
   | `ARA_MAP_ARCHIVOS_SUPABASE_BUCKET` | the private bucket's name |

3. Must not be set: `ARA_MAP_DB`, `ARA_MAP_ARCHIVOS`, `ARA_MAP_READ_ONLY`
   (except during a deliberate freeze), the assistant's keys
   (`OPENAI_API_KEY`, `ARA_MAP_IA_*`).
4. Deploy **manually** from the reviewed commit. Record the deploy id.

What a wrong setting looks like:

| Symptom | Cause |
|---|---|
| Deploy fails at start: "Falta ARA_MAP_DATABASE_URL" / "Falta ARA_MAP_HOST_PUBLICO" | That secret is missing or malformed |
| Deploy fails at start: "La base está en el esquema …" | Step 1.3 was not run against this database |
| Every page answers 403 | `ARA_MAP_HOST_PUBLICO` is not exactly the address in the browser |
| The portal works but uploads and downloads answer 503 | A storage secret is missing or wrong, or the storage project is paused or full |

The service never starts on SQLite and never keeps files on its own disk.

## 4. Accounts and grants

```sh
python scripts/cuentas.py --url-env PILOTO_DB crear <login> "<Nombre visible>" --rol admin
python scripts/cuentas.py --url-env PILOTO_DB crear <login> "<Nombre visible>"
python scripts/cuentas.py --url-env PILOTO_DB listar
python scripts/cuentas.py --url-env PILOTO_DB restablecer <login>
python scripts/cuentas.py --url-env PILOTO_DB desactivar <login>
```

Passwords: hidden prompt, 12 characters or more, handed over outside chat and
outside the repository. There is no self-service reset. An operator sees
nothing until an administrator grants a work base in the portal
(**Bases de trabajo y accesos**).

## 5. Loading the first 50–100 terrains

The portal's Excel/CSV import fills only the old imported-bases workspace; it
does **not** put rows in the editable table. The load is an operator command,
**run as initial setup before employees start working in that base.** It does
not lock the base against a simultaneous change by an administrator (an
archive of the base committed mid-load is not waited for), and employees
editing while it runs could create a terrain the load then cannot see as a
duplicate. Run it while nobody else is working in the base:

1. An administrator creates the work base in the portal and grants it.
2. Save the spreadsheet as CSV UTF-8. Recognized headers are the import's own
   (`Terreno`, `Estado`, `Municipio`, `Superficie m2`, `Asking Price`, `X`,
   `Y`, …). **X is the latitude and Y the longitude.**
3. Dry run, read the report, then the real run:
   ```sh
   python scripts/cargar_maestra.py --url-env PILOTO_DB --base "<nombre exacto>" --admin <login> --dry-run terrenos.csv
   python scripts/cargar_maestra.py --url-env PILOTO_DB --base "<nombre exacto>" --admin <login> terrenos.csv
   ```
   Options: `--moneda MXN|USD` when the prices have one currency;
   `--decimales comma` for comma decimals.
4. What it does: one transaction, all or nothing; an invalid value stops the
   whole load. A terrain already in the base (same name, state, municipality
   and area) is skipped and listed, never duplicated or updated. Rows without
   a name and unrecognized columns are listed and not loaded. Nothing is
   converted or calculated.

## 6. First-day checks (the hosted gate; synthetic files and fictional accounts)

Pass/fail lines for the hosted report, with times and sizes:

1. After 20 idle minutes: time from first request to a usable login page.
2. Sign in as administrator and as operator; an operator without the grant
   sees no base.
3. Load 50–100 synthetic rows (section 5); the operator pages, filters, edits.
4. A valid KMZ above 4 MiB and one at 20 MiB: upload, explicit contour
   selection, activation, boundary drawn for a terrain with empty X/Y.
5. An invalid replacement KMZ: the previous boundary is still drawn.
6. A 25 MiB PDF: upload, download, same SHA-256.
7. A second signed-in session with access reads the same file and boundary; an
   account without the base gets the same answer as for a missing file.
8. Access removed, or the terrain archived, while an upload is completing: it
   does not become an available file.
9. Two uploads to the same final name at once (Team B's check): one winner.
10. Redeploy the same commit: rows, files, boundaries and history are intact.
11. Peak memory and duration of the 20 MiB KMZ completion, alone and beside
    one other large transfer.
12. Backup and restore drill (sections 7 and 8).

## 7. Backup (operator-held; daily while the pilot has real data)

A provider's database backup never contains the file bytes. The pilot's
backup is two things kept **together, outside the host and outside the live
bucket**:

1. **Database first.** One consistent snapshot:
   ```sh
   pg_dump --format=custom --no-owner --no-privileges --file piloto-<fecha>.dump "$PILOTO_DB"
   ```
   A dump is a single transaction's view; no write freeze is needed for it.
2. **Files second, for exactly that dump.** Final files are written before the
   database refers to them and are never changed afterwards, so every file the
   dump refers to still exists when step 2 runs. Restore the dump into a
   scratch local database and give that to Team B's exporter, so the list of
   files is the dump's own:
   ```sh
   createdb ara_respaldo_tmp && pg_restore --no-owner --no-privileges --dbname ara_respaldo_tmp piloto-<fecha>.dump
   ```
   then run B's verifier/exporter against `ara_respaldo_tmp` and the live
   bucket, into the backup folder. It checks every referenced file's size and
   SHA-256 and reuses files already exported on earlier days, so a daily
   backup does not re-download everything.
3. A backup counts only when the exporter reports **zero** missing or
   inconsistent files. Note the date, the dump's size and the files' total.
4. If a moment with no activity is preferred, set `ARA_MAP_READ_ONLY=1` on the
   service for the duration: people already signed in keep reading; signing in and every
   write answer 403.

Also on each backup day: read the storage usage (against 700 MB) and the
database usage in the provider dashboards and write them down.

## 8. Restore drill (once before real use; into fresh targets only)

Never restore over the running pilot.

1. New empty database. `pg_restore --no-owner --no-privileges --exit-on-error
   --dbname "$RESTAURADA_DB" piloto-<fecha>.dump`.
2. **Before anyone can reach it**, clear the operational tables. A full dump
   contains them:
   ```sql
   BEGIN;
   DELETE FROM team_session;        -- everyone signs in again
   DELETE FROM team_login_failure;  -- no stale lockouts
   DELETE FROM archivo_trabajo;     -- no processing turn survives a restore
   COMMIT;
   ```
   Confirm which database the variable points at before running it.
3. New private bucket; upload the exported files with B's tool.
4. B's verifier against the restored database and the new bucket: every
   referenced final file present with its recorded size and SHA-256; history,
   attempts, geometry and active boundaries linked. Unreferenced objects are
   reported, never deleted.
5. Uploads that were pending at backup time come back pending, with their
   original deadlines and without their staged bytes: they are reported; the
   person cancels and starts again, or they expire.
6. Point a **separate** service at the restored pair and repeat checks 2, 3
   and 7 of section 6.

The database half of this drill was rehearsed locally (see START_HERE); the
file half needs B's tool and the real providers.

## 9. Identities to record

Commit SHA · Render service and deploy id · Python version in the build log ·
Neon project, database and role names · Supabase project and bucket names ·
usage figures on the day · who ran each step and when. Never the secrets.

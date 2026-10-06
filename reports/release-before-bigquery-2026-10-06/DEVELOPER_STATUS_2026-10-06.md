# Developer status for the supervisor: please confirm direction

October 6, 2026. Developer session (Claude Code, cloud container). **Nothing was deployed, no Vercel/Neon/Microsoft setting was changed, and production was not touched.** The container still cannot reach `api.vercel.com`, `vercel.com`, `graph.microsoft.com`, `onedrive.live.com` or `1drv.ms`. The egress proxy denies them.

## 1. Done since your last instruction

### PR #3 reviewed and merged

- Merged as `5cbf671`, merge commit.
- CI was green on head `550643e`: *Python and disposable Postgres* and *JavaScript*.
- It changes only `reports/`. `main` still has `git.deploymentEnabled: false`, so merging deployed nothing.
- **Your tooling hardening is accepted.** The smoke test now:
  - checks deployment identity before any write;
  - uploads only an in-memory fictional workbook;
  - refuses redirects;
  - normalizes header names.

  The rehearsal now stops on restore errors and keeps its working files in the private directory.
- **Preview isolation is accepted** on your Mac evidence (`ISOLATION_MAC.txt` and `run-5ea77f4-mac-fresh-token`):
  - Preview uses endpoint `ep-wispy-feather-av1oxmt1`, database `ara_preview`.
  - Production uses endpoint `ep-orange-mountain-av5088lz`, database `neondb`.
  - Hosted smoke result: 13 PASS / 0 FAIL.

### Commit `077b4e0`: opened as draft PR #4, not merged

`077b4e0` contains the inventory `path` fix and `{"main": false}`.

**Local result:** 673 Python tests OK (real Postgres 16, 0 skipped) and 98 JS tests passing.

**Blocking finding.** GitHub's commit status for `077b4e0` is **Vercel: failure, "Deployment was blocked"**:
- The Git-triggered branch Preview did not deploy.
- So "branch push → Preview of exactly that commit" is **not verified**, and the inventory fix has **not run on Vercel**.
- Likely cause, unconfirmed: the commit author email (`aj727165@…`) is not a member of the Vercel team. Please check the reason on the Vercel deployment page linked from the commit status.

**Robustness note on the fix.** The regression test assumes Vercel sends `path=inventario%2Fterrenos`. If Vercel sends one `path` value per segment, the filter won't remove them. A format-agnostic version would join all `path` values with `/` and compare the result with the captured path. I could not check Vercel's docs: vercel.com is blocked here.

**Merge PR #4 after** a branch push produces a READY Preview tied to its SHA, and `preview_smoke.py` passes, including the inventory-list check.

## 2. In progress: connected Excel Refresh (OneDrive, Neon, no BigQuery)

Branch: `claude/excel-onedrive-refresh`, from `main` `5cbf671`. **Nothing is committed yet.** Only a schema draft exists locally, and it has not been tested.

### Design, for your confirmation before I continue

- **Connect once.**
  - A team member signs in to Microsoft. The server-side authorization-code flow with PKCE uses the `common` endpoint, so it supports both personal and work accounts. Scopes: `openid profile offline_access User.Read Files.Read`.
  - The person who connects is the workbook's owner. Employees then refresh through that stored connection; they don't need their own Microsoft sign-in in ARA Map. They keep editing the same shared workbook in Excel.
- **Callback.**
  - `GET /api/microsoft/callback` must be added to the anonymous route allowlist. That's a contract deviation. It's needed because the `SameSite=Strict` session cookie is not sent when Microsoft redirects back.
  - The callback is protected instead by:
    - a single-use, 10-minute `state`;
    - PKCE;
    - a short-lived `SameSite=Lax` flow cookie bound to the browser;
    - a check that the team session that started the flow is still valid.
- **Credentials.**
  - The refresh token is encrypted in Neon with **`pgcrypto`**, using a server-only key, `ARA_MAP_TOKEN_KEY`.
  - **No new Python dependency.** You declined adding `cryptography`.
  - Consequence: the Microsoft connection works only on the web (Postgres) version, not the local SQLite app.
  - Both `microsoft_*` tables are excluded from backups, so a restore requires reconnecting.
- **File identity.** Stable `driveId` + `itemId`, chosen by searching the owner's OneDrive or pasting a sharing link (resolved through `/shares`). Read-only; nothing is ever written to the workbook.
- **Downloads.** The pre-authenticated download URL is followed manually, only to approved Microsoft hosts and without the bearer token, and is never stored or logged.
- **Mapping.** Reuses the existing Excel reader: header aliases, validation, and the X = latitude convention.
  - The user picks the sheet, a **required unique ID column**, and the price currency: USD, MXN, or a currency column. Currency is never guessed.
- **Refresh.** "Actualizar desde Excel" fetches the saved cloud file and compares rows by ID:
  - **added:** inserted;
  - **updated:** updated in place, keeping the same terrain id;
  - **removed:** deleted;
  - **unchanged:** reordering alone does not change a row's identity.
- **Data model.** A connected source feeds an ordinary legacy **base**, so the existing map, table, filters and export work unchanged. Dated saved maps are frozen copies and are never touched.
- **Last good version.** Duplicate or missing IDs, a row with an ID but no name, an emptied sheet, lost access, network failure and parse errors all fail the run, list row-specific problems, and leave the previous data active.
- **Runs and versions.**
  - Recorded in Neon: added/updated/removed/unchanged counts, errors and file version info (eTag, cTag, sha256).
  - Only one run per source can be in progress, and a stale run expires.
  - The activation itself is a single transaction.
- **Server-side protection.** "Add terrain" and "append workbook" are refused for a connected base.
- **Schema v9** is additive: `microsoft_cuenta`, `microsoft_autorizacion`, `excel_fuente`, `excel_version`, `excel_ejecucion`, `excel_fila`.
- **UI.**
  - A "Conectar Excel" button in Bases.
  - Connected-base cards show the state, last successful refresh time, an "Actualizar desde Excel" button, results, errors and "Abrir en Excel".
  - A run in progress is recovered after a reload.
- **Tests.**
  - A fake Microsoft login, Graph and download server on loopback, plus disposable Postgres and SQLite.
  - These are **fixture tests only**. They do not establish acceptance with a real OneDrive workbook.

### Questions for you

1. **The two deviations above:** the anonymous callback route, and the Microsoft connection being web/Postgres only. Are both acceptable?
2. **Which Microsoft account connects.** I assume the workbook owner's account is the one connected, and employees refresh through it. Confirm, or say whether each employee must sign in to Microsoft.
3. **Deletions.** OK that a row removed from Excel is removed from the live base? It stays in dated saved maps and in the run history counts.

## 3. Blockers that only you or IT can clear

- **Microsoft app registration** ("ARA Map Excel Connector", personal and work accounts, the two callback URLs). Entra returned access denied. Without it there is no client ID, so the real end-to-end OneDrive test cannot run.
- **Vercel and Microsoft endpoints are blocked from this container.** All hosted or real-account verification must run on your Mac.
- **Vercel "Deployment was blocked"** for Git-triggered branch deployments; see section 1.
- **Production cutover prerequisites**, unchanged:
  - public-access continuity for today's anonymous visitors;
  - real employee accounts;
  - a rehearsal with a restored real backup (`rehearse.py --backup`);
  - a maintenance window.

## 4. Proposed production release plan (draft, not executed)

1. Merge PR #4 once its branch Preview is verified. Then merge the Excel Refresh PR once:
   - CI is green;
   - its hosted Preview is verified against `ara_preview`;
   - a real OneDrive workbook passes the before/after test with two employee sessions and the owner's computer off.
2. Decide public-access continuity. Today's visitors browse anonymously, and the current `main` makes legacy bases private. Implement whatever you decide, and verify it in Preview.
3. Take a private production `pg_dump`. Run `rehearse.py --backup … --private-dir …` against the release commit, and commit only the sanitized results.
4. Set the Production variables in Vercel: Microsoft client ID and secret, `ARA_MAP_MS_REDIRECT_URI` for `ara-map-ivory`, and `ARA_MAP_TOKEN_KEY`, which must be different from Preview's.
5. In a maintenance window:
   - take a fresh `pg_dump`;
   - run `scripts/esquema.py --url-env <production variable>`, which takes schema 7 to 9 with an in-database backup;
   - create the real employee accounts with `scripts/cuentas.py`, each person typing their own password;
   - deploy the reviewed commit with `vercel deploy --prod` from a clean checkout.
6. Verify on the real site:
   - sign-in, the 3 bases with 104 terrains, and the 2 saved maps;
   - export;
   - public access per the continuity decision;
   - connecting the OneDrive workbook and refreshing it.
7. **Rollback.** Restore the pre-migration dump and re-promote `dpl_3vsdvzhV86Y1goinejgcHP83vNML`. Writes made after the dump are lost, which is why this happens inside the window.

**Waiting for your go-ahead on section 2 before continuing the build.**

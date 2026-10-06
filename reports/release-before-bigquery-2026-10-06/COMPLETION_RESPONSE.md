# Completion response: connected Excel Refresh before BigQuery

Date: 2026-10-06. Developer: Claude Cloud session (lead for Tracks B and C). This is a checkpoint report, not a release claim. **No acceptance scenario that needs hosted Vercel, Neon or Microsoft is marked passed.**

```text
Instructions followed: reports/release-before-bigquery-2026-10-06/SUPERVISOR_COMPLETION_INSTRUCTIONS_2026-10-06.md
                       and COORDINATION.md, both at 3c486f9 (branch codex/supervisor-completion-brief, PR #5, read before merge)
Implementation:        claude/excel-onedrive-refresh, 415eb2640a42d99687fcef7a68ac3575ce8a651e,
                       https://github.com/Andre07-hash/ARA-MAP/pull/6 (draft; base main 5cbf671)
Report:                reports/release-before-bigquery-2026-10-06/COMPLETION_RESPONSE.md on the same branch
                       (the report commit follows 415eb26 and changes only this file)
Local-only/uncommitted work: none. The disposable Postgres cluster and test servers in the container are not evidence carriers.
Local tests:           at 415eb26, see section 5. Python 720/720 on Postgres 16.14 (0 skipped), 720 on SQLite (49 Postgres-only skipped),
                       JavaScript 110/110, browser e2e 11/11, ruff and mypy clean.
Hosted tests:          BLOCKED from this container (the proxy denies Vercel, Neon and Microsoft). No hosted run at this SHA.
Production changes:    none. Production stays dpl_3vsdvzhV86Y1goinejgcHP83vNML, schema 7.
Remaining blockers:    section 6 (Track A diagnosis, Microsoft registration, Preview secrets and pgcrypto, hosted and real-OneDrive verification,
                       the public-continuity business decision).
Requested review:      section 9.
```

Commits on PR #6, oldest first:

| SHA | Scope |
|---|---|
| 8d7c8f1 | Untested schema-9 draft (superseded; kept as history) |
| 190e0ed | Track B: corrected schema 9, versioned refresh, identity, history, idempotency, fencing |
| c31a3e3 | Track C server: OAuth and PKCE, pgcrypto credentials, Graph provider, fake Microsoft, DR invalidation script |
| 9a55e3f | Track C UI: connect, review, refresh, recovery; browser e2e; runs record who started them |
| 47fd852 | Section 9: write freeze enforced by the database, plus 503 "mantenimiento" |
| 250a6af, 415eb26 | Explicit schema 8→9 migration checks; a lint fix |

PR #4 (codex/fix-vercel-inventory-api, 077b4e0) is unchanged and still draft. Its GitHub Actions CI passes, but Vercel reports "Deployment was blocked" (section 6, A1). PR #6 does not include PR #4's adapter fix and does not depend on it. The two must be integrated before a release candidate exists, so **there is no integrated release SHA yet.**

## 1. Decisions implemented from the brief

| Brief item | Implemented as |
|---|---|
| 2A: callback on the anonymous allowlist, with controls | `GET /api/microsoft/callback` is the only new anonymous route (server/auth.py, citing the brief). It accepts nothing but `code`/`state`/`error`, always answers 303 to `/#/bases?excel=conectado/error/cancelado` with `no-store` and `no-referrer`, and clears the flow cookie. |
| 2B: web/Postgres-only connector | Available only when Postgres, the key and pgcrypto are present. The local SQLite app says "sólo está disponible en la versión web" (browser-verified). |
| 2C: pgcrypto | `pgp_sym_encrypt` with AES-256, plus a key version. No new pip dependency. |
| Owner connects once, employees refresh with an audit | `excel_cuenta.conectada_por` records the connecting user. Every run records `iniciada_por`, and the cards show "Iniciada por Ana …". |
| Excel deletions | Removed from the live view and kept in immutable history (identity tombstones). An empty candidate needs a confirmation bound to its exact fingerprint. |
| Section 4 corrections | All of them; see section 2. |
| Section 5: Microsoft | No `/shares`. A picker over the connecting account's own drive (`/me/drive`). Scopes `offline_access User.Read Files.Read`. Redirect-host validation, size and ZIP bounds, Retry-After. |
| Section 6: run contract | A bounded synchronous request with a durable run and lease (deviation note below). |

**Deviation, stated rather than hidden: synchronous refresh.** A refresh is one HTTP request. The server claims the run (short transaction), fetches and parses with no database session open, then activates under a fence (short transaction) and answers.

- Nothing continues after the request ends. There is no 202 and no Python thread.
- If the function dies (Vercel's 120 s `maxDuration`, a crash, a closed tab), the run row stays `en_curso` until its 100 s lease ends. The next read or claim marks it `interrumpida`. The previous version stays active throughout.
- A late worker cannot activate: activation checks lease ownership, the source generation and the configuration (`SinPropiedadError` / `ConflictoError`).
- **Impact:** a workbook that takes longer than about 100 s to download and parse never refreshes. Downloads are capped at 10 MB, so this is not expected; it would need a durable worker, which the brief allows as the alternative.
- We do not claim unattended completion.

## 2. Schema 9, identity, run contract, transactions

**Tables** (server/db.py `EXCEL_SCHEMA`, mirrored for Postgres by `postgres.excel_sql()`). There are no `ON DELETE CASCADE` on connector tables, and the 8→9 test asserts it.

| Table | Purpose |
|---|---|
| `excel_cuenta` | Account identity, unique on (provider, tenant, account ID); personal or organization. |
| `excel_credencial` | Split from the account: encrypted refresh token, key version, generation, refresh lease (`ocupada_hasta`, `ocupada_por`). |
| `excel_autorizacion` | Pending sign-ins. Only hashes and the encrypted PKCE verifier are stored; entries expire after 10 minutes. |
| `excel_fuente` | One per connected base (`base_id UNIQUE`, no cascade). Unique on (`drive_id`, `item_id`). Holds state, active configuration and version, generation (the CAS fence) and the times of the last check, success and error. |
| `excel_configuracion` | Versioned: sheet, ID column, currency (`USD`, `MXN`, `desconocida` or `columna`, with a CHECK pairing it to the currency column), reader version, fingerprint. |
| `excel_version` | Immutable activated versions: file SHA-256, order-insensitive content fingerprint, row count, confirmed-empty flag. Composite FK to its configuration. |
| `excel_identidad` | Durable registry from Excel ID to terrain: first, last and deleted-in version. Re-adding an ID revives its identity. |
| `excel_version_fila` | Immutable row snapshots per version and identity (normalized record JSON plus fingerprint). |
| `excel_ejecucion` | Runs. See the run contract below. |

**`excel_ejecucion` (runs):**
- `tipo` is `conexion` or `actualizacion`.
- `estado` is one of `en_curso`, `ok`, `sin_cambios`, `revision`, `error`, `interrumpida`, `conflicto`.
- `UNIQUE (fuente_id, clave_idempotencia)` plus a request fingerprint; a partial unique index allows one `en_curso` run per source.
- It also holds the lease, base generation and configuration, non-negative counts, and the safe error code and message. Row problems are stored as JSON.
- CHECK: `en_curso` if and only if `terminada_en` is NULL.

**Identity.** Rows match only by the exact text of the configured ID column.
- IDs keep leading zeros. An integral float becomes an integer string.
- Booleans and dates are rejected as IDs. Nothing is case-folded.
- An ID is never inferred from row position or name.
- Missing or duplicate IDs, a missing name, unreadable numbers and unsupported currencies block activation with row-specific problems.
- Reorder-only or packaging-only changes give `sin_cambios` with no new version.

**Idempotency.**
- Refresh: `Idempotency-Key` is required. The same key and body replays the recorded run; the same key with a different body gives 409 `idempotency_conflict`.
- Source creation: `inventory_operation_result` (`excel_conectar`) with a fingerprint, plus a unique-violation fallback. No duplicate base or source is created.
- Client side: a lost answer is retried promptly (within 2 minutes) with the same key. A reload never replays an old request; the server's state is shown instead. This last behavior was found and fixed during browser testing.

**Transaction boundaries.**
1. Claim: short transaction.
2. Fetch and parse: **no session**. This is verified twice: a Postgres test asserts no session is held during download, and a probe showed concurrent requests are not blocked during a 4 s download.
3. Activate: short fenced transaction (identities, snapshots, terrain upsert/delete, version pointer, counts).
4. Token refresh: its own credential lease, with CAS on `ocupada_por` and `generacion`.

**Write restrictions** are server-side. Append, add-terrain and delete on a connected base return 409 `fuente_conectada`, including after the source is disconnected. Rename and move remain allowed. Saved (dated) maps are snapshots and are tested unchanged after a refresh.

## 3. OAuth, scopes, credentials, restore

**Endpoints** (signed-in team members, except the callback):
- `GET /api/microsoft/estado`, `POST /api/microsoft/conectar`, `GET /api/microsoft/callback` (anonymous, controlled)
- `GET /api/microsoft/cuentas/:id/archivos`, `POST /api/microsoft/cuentas/:id/olvidar`
- `GET /api/excel/fuentes[/:id[/versiones[/:vid]]]`, `POST /api/excel/vista-previa`, `POST /api/excel/fuentes`
- `POST /api/excel/fuentes/:id/actualizar`, `POST /api/excel/fuentes/:id/configuracion`
- `POST /api/excel/fuentes/:id/desconectar`, `POST /api/excel/fuentes/:id/reconectar`

**Flow.** Authorization code with PKCE (S256), `response_mode=query`, `prompt=select_account`.
- State is single use; only its SHA-256 is stored, with a 10-minute expiry.
- The flow is bound to the browser by an `ara_ms_flujo` cookie (HttpOnly, Secure, SameSite=Lax, Path=/api/microsoft/callback; only its hash is stored). It is also bound to the starting session and user.
- The flow row is claimed (deleted) before the code exchange, so replays find nothing. The session is re-checked after the exchange.
- Authorities: `common`, `consumers`, `organizations` or a tenant GUID. Accounts are typed personal or organization from `driveType`, and the same account reconnects onto the same row.

**Scopes:** `offline_access User.Read Files.Read`. `Files.Read.All` is not requested, because the workbook is read from the connecting owner's own drive.

**Downloads.** `/drives/{d}/items/{i}/content` is followed manually through at most 3 redirects, without the bearer token.
- Allowed hosts are matched by DNS label: `*.1drv.com`, `*.sharepoint.com`, `onedrive.live.com`, `files.1drv.com`.
- Other limits: 10 MB download, 80 MB expanded, 2000 ZIP members, 20000 rows, 200 columns.
- 429/503 retries follow Retry-After within a 10 s budget and at most 3 retries (the cap was added after a fake test showed `Retry-After: 0` could loop).
- Error messages never include URLs.

**Credentials.**
- Refresh tokens are stored as `pgp_sym_encrypt(…, 'cipher-algo=aes256')` under `ARA_MAP_TOKEN_KEY` (at least 32 characters) and `ARA_MAP_TOKEN_KEY_VERSION`.
- A wrong or changed key version gives "reconnect required". A missing key or a missing pgcrypto disables only the connector; the rest of the app keeps working (tested).
- **Rotation:** set a new key and version, then reconnect each account. Old ciphertext is never decrypted with the new key.
- Rotated refresh tokens are written back under the credential lease. On `invalid_grant` the credential is deleted.

**Restore policy.**
- *Content backups* (`postgres.TABLES`) never contain credentials or pending sign-ins. A restored source shows "Hay que volver a conectar la cuenta" and keeps its identity and history (tested).
- *Private DR restores:* run `scripts/invalidar_restauracion.py --url-env VAR [--olvidar-credenciales]` before serving traffic. It ends sessions and login throttling, deletes pending sign-ins, marks running refreshes interrupted, and optionally forgets credentials (tested).

## 4. Production continuity, rehearsal, provisioning, release (section 9)

**Implemented and tested: the server-enforced write freeze.** `scripts/congelar_escrituras.py --url-env VAR estado|activar|desactivar` sets `default_transaction_read_only` on the target **database**, ends its other connections, and reports in-progress refreshes.
- Every deployment, including older Vercel deployment URLs with their own environment, then refuses writes with 503 `mantenimiento` (Retry-After 300). Reads, existing sessions and export keep working; new logins are refused.
- The release's own migration session overrides the freeze for itself only, through a direct (unpooled) URL with `options=-c default_transaction_read_only=off`.
- Tested on a dedicated disposable database through two adapter instances.
- Operator check on Neon: the owner role must be able to `ALTER DATABASE` and terminate backends. Read `conexiones_terminadas` and `otras_conexiones` from the output.

**Public continuity: not implemented. A business decision is needed.**

From the frozen schema-7 baseline (`reports/inventory-developer-handoff-2026-10-05/verification/baseline_src/api/index.py`), today's production lets **anonymous visitors**:
- read `GET /api/bases`, `/api/bases/:id`, `/api/bases/:id/terrenos`, `/api/mapas`, `/api/mapas/:id`, `/api/mapas/:id/terrenos` and `/api/carpetas`, with all fields;
- export through `POST /api/exportar`.

Only writes and import configuration required the shared password. Current main requires sign-in for all of these.

I could not compare against the live site, because production is unreachable from here. Proposed manifest:
- At release, freeze the IDs of the bases and saved maps present in the verified final backup into a `publico_legado` manifest. The last verified counts are 3 bases, 104 terrains and 2 maps; derive the actual counts from the fresh backup.
- Serve exactly those anonymously, read-only, with the same fields and export. Folder names appear only where they contain a manifest item.
- Everything created later stays private, including every connected Excel base.
- The operator runs a field-by-field comparison script against old production and the staged build.

**Decision for the owner:** keep those legacy bases and maps public as-is after the release, or retire anonymous access to them.

I will implement the manifest once that answer arrives. It is a narrowly scoped server and UI change of about one day with tests.

**Rehearsal: not yet updated.** The existing `rehearse.py` encodes schema 8 and "an empty public catalog", which the continuity decision changes.
- Covered now by tests: 8→9 (explicit tables, data preserved, repeatable, no cascades, backup exclusions), 5→9 through the real migration script, fresh 9, repeated migration, connected-source history, and content restore with reconnect.
- Still to be written as a new dated rehearsal, after the decision: 7→9 from the frozen baseline builder; the real backup restored into an isolated environment by the operator; rollback to the schema-7 code; and expected counts derived from the backup.

**Employee provisioning: mechanism exists, names needed.** `scripts/cuentas.py` creates and disables named accounts (`--password-stdin`; no shell access is needed by employees).
- Needed from the owner: account names, and a delivery method, such as a password manager share or an in-person handover.
- A self-service first-login password change is not implemented. Propose it if the owner wants operators never to know passwords.

**Staged release, proposed sequence** (needs the decisions above and section 6):
1. Owner approves the release gate.
2. `congelar_escrituras activar` on production, then wait for in-progress refreshes to finish (at most 100 s).
3. Take a private `pg_dump` and verify its hashes and counts.
4. `migrate_cloud.py --url-env` through the direct, unfrozen session, then `CREATE EXTENSION pgcrypto` as owner.
5. Provision accounts.
6. `vercel deploy --prod --skip-domain` with production secrets (ARA_MAP_MS_* for **production**, ARA_MAP_TOKEN_KEY); run non-destructive checks only.
7. Promote.
8. Verify OAuth on the real domain, which the staged host cannot prove.
9. `congelar_escrituras desactivar`.

**Rollback while still frozen:** restore the dump into a new branch or database, point production at it, and promote the previous deployment `dpl_3vsdvzhV86Y1goinejgcHP83vNML`. Never run schema-7 code on schema 9. After writes reopen, no blind restore: freeze, reconcile, and ask for a decision.

## 5. Evidence, kept separate by category

| Category | Result at 415eb26 | Command or location |
|---|---|---|
| Local fixture (in-memory provider, SQLite) | Python 720 tests OK (49 Postgres-only skipped); 28 connector tests in `tests/test_excel.py` | `python -m unittest discover -s tests -t .` with no DB URL; Python 3.11.15 |
| Local real Postgres 16.14 (disposable, psycopg 3.3.6) | 720/720 OK, **0 skipped**. Includes connector core (`test_excel_postgres`, 8 tests), OAuth and Graph against the local **fake Microsoft** through the cloud adapter (`test_excel_microsoft_postgres`, 10 tests), write freeze (2), and 8→9 migration (1) | `ARA_MAP_TEST_DATABASE_URL=postgresql://…@127.0.0.1:55432/… python -m unittest discover -s tests -t .` |
| JavaScript | 110/110 (includes 11 new `excel.test.mjs` tests and a router test) | `node --test tests/js/*.test.mjs` |
| Browser, local (Chromium 1194, cloud adapter, disposable Postgres, fake Microsoft) | **11/11** (scenarios below) | `tests/e2e/excel_servidor.py` plus `tests/e2e/excel-conectado.mjs` (instructions in their headers) |
| Static | ruff (server, tests, new scripts) clean; mypy on 54 files clean | `verificar.sh` equivalents |
| CI (GitHub Actions, Postgres 16) | Not yet reported for 415eb26 when this was written; check PR #6 | |
| PostgreSQL 18 / Neon | **Blocked.** Only PG 16 is installable in this container | Operator, section 6 |
| Hosted synthetic workbook (Vercel Preview) | **Blocked** | Operator, section 6 |
| Real Microsoft account and workbook | **Blocked** (no app registration; Microsoft unreachable) | Operator, section 6 |

The browser e2e cases, in order:
1. Connect the owner account, pick the workbook, review and import.
2. The connected card shows only safe actions; "Abrir en Excel" uses `noopener noreferrer`; no horizontal overflow at 1440 and 390 px.
3. Another employee refreshes with real counts; no duplicate base; the map reloads; repeated refresh reports no change.
4. A double click sends exactly one request.
5. An in-progress run is seen from another browser and across a reload, settles by bounded polling, and the old data stays visible.
6. An empty candidate is cancelled, then confirmed.
7. Invalid rows list row diagnostics and nothing is applied.
8. A revoked grant keeps the data and is fixed by reconnecting.
9. Cancelling at Microsoft is safe.
10. Anonymous requests get 401, and the callback only redirects.
11. The local SQLite app reports the connector as web-only.

Screenshots were reviewed in the session and are not committed.

## 6. Remaining access actions (authorized operator, not the supervisor)

- **A1. Diagnose PR #4 (Vercel account holder).** Open https://vercel.com/aicore2/ara-map/7LZ7D4z71j5jbCqrAH1Wpi7YS1BF and record the exact "blocked" reason.
  - Do not change commit authorship or disable protection.
  - If it is a team-membership or Git-author block, the account holder links or approves the GitHub author per Vercel's supported flow.
  - Then capture a READY Git-triggered Preview at the reviewed SHA, plus a sanitized `path` parameter shape from one diagnostic request.
- **D1. Register the Microsoft app** "ARA Map Excel Connector" in a directory where the operator has permission, or a personal Microsoft developer account if company Entra stays denied.
  - Supported accounts: personal plus organizational.
  - Web redirect URIs:
    - `https://ara-map-preview-aicore2.vercel.app/api/microsoft/callback`
    - production `https://ara-map-ivory.vercel.app/api/microsoft/callback`
    - add the final domain if it differs.
  - Delegated permissions: `offline_access`, `User.Read`, `Files.Read`.
  - Return only the client ID, the supported account types and the redirect list.
- **D2. Preview configuration.** Add Preview-only secrets `ARA_MAP_MS_CLIENT_ID`, `ARA_MAP_MS_CLIENT_SECRET`, `ARA_MAP_MS_REDIRECT_URI` (the Preview callback), `ARA_MAP_MS_AUTHORITY=common`, `ARA_MAP_TOKEN_KEY` (random, 32 or more characters) and `ARA_MAP_TOKEN_KEY_VERSION=1`.
  - On Neon branch `preview-ficticio`, as the branch owner: `CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;`.
  - Then run `migrate_cloud.py --url-env` against the Preview URL only.
- **D3. Hosted verification at the integrated SHA** (PR #4 merged with PR #6):
  - Rerun the expanded smoke test, then repeat the browser scenarios on the Preview with a fictional workbook in a dedicated personal OneDrive.
  - Then real before/after edits by a second employee, with the owner's Mac off.
  - Also: PG 18/Neon suite evidence (`ARA_MAP_TEST_DATABASE_URL` on a disposable Neon branch) and a recheck of database isolation.
- **O1. Owner decisions:** public continuity (section 4), employee names and delivery method, and the release window.

These can proceed independently now:
- the public-manifest implementation, once O1 is answered;
- the new dated rehearsal;
- merging PR #4's fix into PR #6 once A1 explains the block.

## 7. Acceptance checklist (section 8)

**Local** means local fixture, Postgres and browser with the fake Microsoft. Nothing here is hosted or real-Microsoft evidence.

| Scenario | Local | Hosted synthetic | Real Microsoft |
|---|---|---|---|
| First connection | Passed (e2e 1, OAuth tests; no anonymous access) | Blocked | Blocked |
| Normal saved edit | Passed (e2e 3; counts; no reselection or duplicate) | Blocked | Blocked |
| Stable identity | Passed (reorder, insert before, rename, remove and re-add) | Blocked | Blocked |
| No change | Passed (repeat and reorder-only give `sin_cambios`; last-checked advances) | Blocked | Blocked |
| Invalid input | Passed (missing or duplicate ID, missing name, malformed, unsupported currency or mapping, oversized download, ZIP expanded-size limit) | Blocked | Blocked |
| Empty candidate | Passed (bound confirmation; atomic activation) | Blocked | Blocked |
| External failures | Passed against the fake: revoked, deleted, 429, 5xx, disallowed redirect; no URL or token leaks. A real network timeout is not exercised | Blocked | Blocked |
| Changed interpretation | Passed (configuration change re-evaluates the same content) | Blocked | Blocked |
| Request replay | Passed (lost response, double click, same key, conflicting key) | Blocked | Blocked |
| Concurrency | Passed (two users; stale worker fenced; token refresh across two sources) | Blocked | Blocked |
| Process or browser failure | Passed (reload mid-run, lease expiry gives `interrumpida`, bounded polling) | Blocked | Blocked |
| File changes mid-refresh | Passed (coherent revision or retry, then `conflicto`) | Blocked | Blocked |
| Frozen saved maps | Passed | Blocked | Blocked |
| Server write restrictions | Passed (append, add, delete refused; ordinary bases unaffected) | Blocked | n/a |
| OAuth defenses | Passed (wrong, missing, expired or reused state; flow cookie; logout or deactivation during flow and exchange; concurrent replay; account switch) | Blocked | Blocked |
| Recovery | Passed (content restore then reconnect; DR invalidation) | Blocked | Blocked |
| Independence from the Mac | n/a locally | Blocked | Blocked |

No scenario is marked done for release. Every one still needs its hosted and real-Microsoft observations.

## 8. Notable fixes found while testing this checkpoint

- `/api/microsoft/estado` opened a nested workspace session and deadlocked on the advisory lock. It now computes availability first.
- An unbounded retry loop on `Retry-After: 0`. Retries are now capped.
- A stale pending Idempotency-Key replayed an old outcome after a reload. Keys are now in memory with a 2-minute retry window.
- Run DTOs exposed only a user ID. They now carry the display name for the audit trail.
- Refresh times showed only the date. Cards now show the time as well.

## 9. Requested review

1. Do you accept the bounded synchronous refresh (section 1 deviation) for this release, given the 10 MB cap?
2. Do you accept the proposed `publico_legado` manifest (legacy IDs frozen at release; new sources private) as the continuity design, so it can go to the owner as a yes/no question?
3. Do you accept the database-level write freeze as the release freeze mechanism, with the operator checks noted for Neon?
4. Integration order: should PR #4 be fixed and merged into main first and PR #6 then rebased, or should PR #4's adapter fix be merged into PR #6 to produce one release candidate?

# Backend response — Stage 1 (B1 + B2)

October 5, 2026. Local development handoff for supervisor integration review. Nothing was deployed, no production or `.env.local` configuration was read, and no production or local working database was migrated. All evidence comes from the backend developer's own runs on throwaway SQLite files and a throwaway Postgres cluster. It is not independent verification.

## Contract deviations and additions (read first)

None of these changes a frozen envelope, route or field name. Each one either fills a gap the contract left open or adds a field.

1. **Create body is flat.** `POST /api/inventario/terrenos` takes the editable draft fields at the top level (`{"terreno": "...", "moneda": "USD", ...}`), using the same allowlist as PATCH `changes`. Any other key, including `id`, `version`, pointers, actor fields and `extra_json`, gets a 422.
2. **Successful create returns HTTP 200**, not 201, with body `{terreno: InternalTerrain}`. A same-key replay returns the identical stored body, also with 200.
3. **Additive PATCH option `confirm`.** `{"expected_version": N, "changes": {...}, "confirm": ["price", "availability"]}`. It stamps the price and/or availability confirmation with the session user and the current time, and it increments the version. Ordinary edits never change confirmations; they carry them forward unchanged. The attention list needs this, and ATT‑01 depends on it.
4. **Additive `InternalTerrain` fields:** `confirmations`, `source_extra` (raw source extras, read-only, `{}` for direct creates), `revision_number`, `created_at/created_by`, `updated_at/updated_by`, `published_at`. `draft` contains only editable fields.
5. **Currency rule on save.** A PATCH or create that sets a non-null `asking_price`/`asking_m2` while the resulting `moneda` is null gets a 422 on `moneda`. This keeps the existing manual-entry rule: a typed price states its currency. Edits that don't touch prices never fail because an older record has a null currency.
6. **Public catalog routes are Stage 1 placeholders.** `GET /api/publico/terrenos` always returns the empty envelope, and `GET /api/publico/terrenos/:id` always returns a uniform 404. Publish doesn't exist yet, so no record can be eligible. Stage 2 replaces both handlers.
7. **Password KDF is PBKDF2-HMAC-SHA256 with 600,000 iterations**, not scrypt. macOS `/usr/bin/python3` (3.9, LibreSSL) has no `hashlib.scrypt`, and the app must run on it (`test_packaging`). The iteration count is stored in each hash. One hash takes about 0.06 s on 3.14 and 0.14 s on 3.9.
8. **`inventory_source` and `inventory_import_batch` are not created yet.** They belong to Stage 3 (B4). v8 has never been deployed, so they can be added to v8 before release without a v9.
9. **`/api/config` keeps `readOnly`** for the current UI, set to true when signed out. `/api/session` is the authority on sign-in.

## Delivered behavior

- **Individual sign-in with one equal user type.** `team_user` has no role column. Every active account can create, edit, reopen and read the history of every record. The actor always comes from the server-side session. Any actor or server field sent in a body is rejected.
- **Revocable server-side sessions.** The token is 32 random bytes, and only its SHA-256 is stored. Sessions last 12 hours. Logout, expiry, password reset and deactivation each end them.
- **Login throttling is stored in the database**, so all workers share it: 5 failures per login in 15 minutes produces a 429 `rate_limited`. A failed login always gets the same generic 401, and an unknown username costs the same PBKDF2 time as a real one. Login bodies are capped at 4 KB.
- **Shared deny-by-default policy in `server/app.py` `Handler._dispatch`.** The cloud adapter `api/index.py` inherits it and no longer has any auth logic of its own. The anonymous API allowlist is exactly: GET `/api/config`, GET `/api/session`, POST `/api/login`, POST `/api/logout`, GET `/api/publico/terrenos`, GET `/api/publico/terrenos/:id`.
  - Every other `/api/*` path gets exactly 401 `{"error":"Inicia sesión para continuar.","detalle":{"code":"unauthenticated"}}` before routing. This covers unknown paths, all legacy reads and `POST /api/exportar`.
  - A signed-in request to an unknown route gets 404.
  - The check runs on the same normalized path the router uses.
  - Static assets stay public.
  - Old `ara_editor` shared-password cookies grant nothing. `ARA_MAP_PUBLIC_EDIT` and `ARA_MAP_EDIT_PASSWORD` are no longer read, and `server/cloud_auth.py` is deleted.
  - Same-origin checks on unsafe methods are unchanged in both adapters.
  - The cloud returns 503 rather than ever falling back to a SQLite file when Postgres is not configured.
  - All JSON and download responses carry `Cache-Control: no-store`.
- **Schema v8 is additive on both engines.** It adds `team_user`, `team_session`, `team_login_failure`, `inventory_terrain`, `inventory_revision`, `inventory_event` and `inventory_operation_result`.
  - Ids are UUID text.
  - Revisions are immutable (inserted, never updated).
  - The two pointer foreign keys are composite, `(id, draft_revision_id)` and `(id, published_revision_id)` → `inventory_revision(inventory_id, id)`, and `DEFERRABLE INITIALLY DEFERRED`. A pointer can't name another record's revision, and a restore can load the tables in either order. Both engines have a test for this.
  - `UNIQUE(inventory_id, version)` on events.
  - The schema already includes the publication columns for later stages: `published_revision_id`, `published_at`, `first_published_at` (tells never-published apart from unpublished), `archived_at`, `price_on_request`, `availability`, `public_description`, and confirmation at/by.
- **Atomic, version-checked saves.** Each write is a compare-and-set on `inventory_terrain.version` in the same transaction as the new revision, the pointer and the event. A stale version returns 409 `conflict`, and the response includes `current_version` and the current `terreno` so the user can recover. Failure injection confirmed that nothing partial is left behind. A save that changes nothing returns the record unchanged and does not create a version.
- **Idempotent create.** The `Idempotency-Key` header is required (8–200 printable characters); without it the response is 422 `idempotency_key_required` and nothing is written. The key row is the transaction's first write.
  - Same key and same normalized body: the original body is returned.
  - Same key and a different body: 409 `idempotency_conflict`.
  - Concurrent requests with the same key create exactly one record. Tested on both engines.
- **History.** `GET .../historial` returns events newest first with actor `{id, display_name}` as of the event, time, before/after revision ids and per-field `changes: {field: {before, after}}`.
- **Internal list** follows contract §6 exactly: `{terrenos, total, next_cursor, facets}`.
  - Stable id order. The cursor is the last id returned. Page size defaults to 100, maximum 250.
  - Repeated `estado`/`municipio` values are OR within each field and AND across fields.
  - A price filter needs one explicit `moneda`; other and unknown currencies are excluded.
  - Search reuses the existing accent folding (`normalize.fold`).
  - Archived records are excluded unless `include_archived=true` or `publication_state=archived` is requested.
  - Unknown query keys, including private-field selectors, get a 422.
  - Facets cover the whole candidate set rather than the current page, and municipalities narrow to the selected states.
- **Publication gate and attention rules are implemented now in `server/inventario.py`**, ready for Stage 2 publish and preview. The gate is the contract v1 rule set: name; valid coordinates inside Mexico; positive m² or ha; known availability; a positive price in USD or MXN, or `price_on_request` with no amounts.
  - `attention` = gate blockers + never-confirmed price/availability + existing validation findings, such as `PRECIO_INCONSISTENTE`. Findings are warnings only and never correct the source amounts.
  - There is no staleness cutoff.
- **Coordinates follow INTEGRATION_DECISIONS §9.** A half pair, a swapped pair or a pair outside Mexico saves as a draft and shows up as a `location_invalid` blocker. Only nonfinite values, |lat| > 90 or |lon| > 180 get a 422.

## Frozen DTOs as implemented

**Editable draft fields** (`draft.*`, PATCH `changes.*`, create body). Each field is shown with what it accepts:

| Field | Type / rule | Visibility |
|---|---|---|
| `terreno`, `estado`, `municipio` | string or null; whitespace collapsed; max 200/100/100 | public when published |
| `direccion` | string or null, max 500 | public |
| `public_description` | string or null, max 5000 | public |
| `superficie_m2`, `superficie_ha`, `afectaciones_pct`, `afectaciones_m2`, `asking_price`, `asking_m2` | finite number ≥ 0, numeric string, or null | public |
| `lat`, `lon` | finite number within ±90 / ±180, or null | public |
| `moneda` | `"USD"`, `"MXN"` or null (unknown) | public |
| `price_on_request` | boolean | public |
| `availability` | `unknown` / `available` / `negotiation` / `sold` / `withdrawn` | public |
| **`contacto`** | string or null, max 2000 | **private** |
| **`notas_internas`** | string or null, max 10000 | **private** |

**Private and read-only (never in PublicTerrain):** `source_extra`, `confirmations.*.by`, `created_by`, `updated_by`, history and all account data. `confirmations.*.at` are internal dates.

**Example `InternalTerrain`** (response of create, detail, PATCH and list items):

```json
{"id":"b366…","version":2,"draft_revision_id":"aadc…","published_revision_id":null,
 "publication_state":"draft","public_visible":false,"has_pending_changes":false,
 "published_at":null,"archived_at":null,
 "draft":{"terreno":"Lote Uno","estado":null,"municipio":null,"direccion":null,
          "public_description":null,"contacto":null,"notas_internas":null,
          "superficie_m2":null,"superficie_ha":null,"afectaciones_pct":null,"afectaciones_m2":null,
          "asking_price":1000.0,"asking_m2":null,"lat":null,"lon":null,"moneda":"USD",
          "price_on_request":false,"availability":"unknown"},
 "confirmations":{"price":{"at":"2026-10-05T14:38:10-06:00","by":{"id":"65ec…","display_name":"Ana"}},
                  "availability":null},
 "source_extra":{},
 "attention":[{"kind":"blocker","code":"location_invalid","field":"lat","message":"…"},
              {"kind":"unconfirmed","code":"availability_unconfirmed","field":"availability","message":"…"},
              {"kind":"warning","field":"","code":"CAMPO_FALTANTE","severity":"aviso","message":"Falta Estado."}],
 "revision_number":2,"created_at":"…","created_by":{"id":"…","display_name":"Ana"},
 "updated_at":"…","updated_by":{"id":"…","display_name":"Ana"}}
```

**How the server derives the state fields:**
- `publication_state`: `archived` if archived; `published` if there is a published pointer; `unpublished` if the record was published before; otherwise `draft`.
- `public_visible`: published, and the published revision's availability is `available` or `negotiation`.
- `has_pending_changes`: the published pointer differs from the draft pointer. Caveat: an edit that later reverts to identical content still counts as pending.

**Attention codes:**
- `blocker`: `name_required`, `location_invalid`, `area_required`, `availability_unknown`, `price_required`, `currency_required`, `price_conflict`.
- `unconfirmed`: `price_unconfirmed` (omitted when `price_on_request`), `availability_unconfirmed`.
- `warning`: the existing finding codes.

**Other envelopes:**
- Session: `{authenticated:false}` or `{authenticated:true,user:{id,display_name}}`. Login returns the same shape plus `Set-Cookie`. Logout returns `{authenticated:false}`.
- History: `{eventos:[{id,version,action,at,actor:{id,display_name},before_revision_id,after_revision_id,changes,confirmed?}],total,next_cursor}`. `action` is `create` or `update` in Stage 1. The history cursor is a version-number string; query keys are `cursor` and `limit` only.
- Facets: `{estados:[string],municipios:[string],monedas:[string]}`.

**Errors** are `{error, detalle:{code, …}}`:

| Status | `code` | Extra fields / when |
|---|---|---|
| 401 | `unauthenticated` | absent or invalid session |
| 401 | `invalid_credentials` | wrong login |
| 429 | `rate_limited` | login throttle |
| 422 | `validation_failed` | `fields: {name: message}`; bad fields, filters or `expected_version` |
| 422 | `idempotency_key_required` | missing or invalid `Idempotency-Key` |
| 409 | `conflict` | `current_version`, `terreno` |
| 409 | `idempotency_conflict` | same key, different body |
| 404 | `not_found` | absent record or public detail |
| 503 | — | cloud without Postgres |

## Operations (for the verifier and the runbook)

- **Cookie.** The name is `ara_sesion`, set with `Path=/; Max-Age=43200; HttpOnly; SameSite=Strict`.
  - The cloud adapter always adds `Secure`.
  - The local server (`python3 -m server.app`) omits `Secure`. That is the loopback-only cookie setting: the local server binds to 127.0.0.1 and refuses any non-loopback Host header, so it serves `http://localhost`. There is no environment switch for it.
  - Use the local server with `ARA_MAP_DB=<tmp>` on port 8431 for isolated browser tests.
- **Accounts:** `scripts/cuentas.py`.
  - The target is required: `--sqlite PATH` or `--url-env VARIABLE` (the variable holds a Postgres URL). It refuses to run without one and never reads `.env.local`.
  - Actions: `crear USUARIO "Nombre"`, `restablecer USUARIO`, `desactivar USUARIO`, `reactivar USUARIO`, `listar`.
  - The password comes from a `getpass` prompt entered twice, or from `--password-stdin` (one line), never from argv.
  - Rules: login of 3–64 characters `[a-z0-9._@-]`, case-insensitive; password of at least 12 characters.
  - A reset or deactivation ends that user's sessions.
  - Example: `printf '%s\n' "$PW" | python3 scripts/cuentas.py --sqlite /tmp/x/ara.db --password-stdin crear ana "Ana Prueba"`.
- **Postgres schema:** `scripts/esquema.py --url-env VARIABLE [--check]`.
  - Refuses to run without a named target and never reads `.env.local`.
  - Idempotent on both an empty database and an existing workspace. It backs up existing tables to `workspace_backup` first.
  - `--check` exits 0 only when the schema is at 8.
  - Ordinary cloud requests never create or alter schema.
  - `scripts/migrate_cloud.py --url-env …` also brings a workspace to v8. Its default mode is unchanged and still targets production, so do not run it without `--url-env`.

## Files changed (post-change sha256; baseline in `BASELINE_MANIFEST.sha256`)

```
MODIFIED 50931aaff835756f4a4cd2f4f94118212842b115418aabfb47362c29a47c6a6e api/index.py
MODIFIED 9fd4662055c39520b91363996ca780f6f697f4d5c34e6c9eaf9010acd8884d2c server/app.py
MODIFIED b25936ed1721dc4f34b498d1c872b678b927d0c91fa0af6861649fd52ca64d4f server/db.py
MODIFIED 8ff864a95131d70f3032e3a2e06583b16449e3f0a7fd1ef4aac17650c9062320 server/postgres.py
MODIFIED 5dcce6b2250942995cceaea13313bb9470a5419cbe288854a0c3613b5ede1fd6 server/router.py
ADDED    c70b94c2d592490fc246b99def6e895793cd27d1bb49a07bfa076ed491d5c2fa server/auth.py
ADDED    8df71c0705f2a99818545421771fe283d45a8111bba8e574a9f98e9e29363aba server/inventario.py
ADDED    518b49867bdf6f57bf675c32441511b166f7545a77d8e3a4cb19d60103433363 server/repo/inventario.py
ADDED    3d844a743eebc65ec02503f89b240e97358cdaebac5bdbfd2ec5a20ea1cd12c5 server/api/inventario.py
ADDED    44cd87a1153fe3273364e0680e7b9caf6914cb80c618ee5eadc20b2bd5094bbd server/api/sesion.py
ADDED    d49a54ada4cecd6adf013a4ecfbb48122249a4d10f9bc67f1d0578de47125bcb scripts/cuentas.py
ADDED    277f6571fb832eed130f3c79300e01e3526a12224965e496f7899c04598e2eeb scripts/esquema.py
DELETED  server/cloud_auth.py
MODIFIED 91dc037fa79be8c444c818b666076e0aa0af9bfd85a01e9c2f90190a93b44e31 tests/support.py
MODIFIED 659b4e9191f6851ff1d7c90b9c3cd8aded5103206f536cb9b23e3445c850ab3a tests/test_server.py
MODIFIED 02e4a942618902672685e5400cb43c646f2081ae1778b2767fc18c6b4e7d1a2c tests/test_cloud.py
MODIFIED d841ac00a3c9ea2a9dc56abd2cfc3abdf7332b031eea7306cca239989e406dc8 tests/test_carpetas_migration.py
MODIFIED f1ddec239ec8078f8947f17c9b4cee7c84359ea35e3ab5f6fd31aaa5e82cdd6e tests/test_asistente_migracion.py
ADDED    5b3a13762ab9d7cc09e252f6b382289d949e58d50af1a73d8404c94c9e1dafad tests/test_inventario.py
ADDED    a16395ce4dadbadd2c88c7a7eeb5da1f47bb4630a3df42581df34ff609f866ef tests/test_inventario_postgres.py
ADDED    3a1d25812018adf7e19f9ecf0950ae42ce7cd8a612240274a1e9eb17029cb6ec tests/test_cuentas.py
```

All other baseline files in `server/ api/ scripts/ tests/ pyproject.toml vercel.json` are byte-identical to the baseline, excluding `web/`, `tests/js/` and `tests/e2e/`, which belong to the interface developer and verifier. No new dependency was added.

## Changed existing tests (each has a replacement assertion)

- **`test_cloud.py`, rewritten.** It used to assume a shared password, anonymous reads and the `ARA_MAP_PUBLIC_EDIT` bypass. It now asserts:
  - anonymous reads, writes, export and unknown routes get 401 with `no-store`;
  - `PUBLIC_EDIT=1` grants nothing;
  - the anonymous config payload;
  - the anonymous CSV preview gets 401;
  - no SQLite fallback without Postgres (503);
  - individual login: generic 401, the `Secure`/`HttpOnly`/`SameSite=Strict` cookie, the session payload, and that logout revokes the session on the server;
  - forged, expired and cross-origin requests fail;
  - a password reset or deactivation ends sessions;
  - per-account throttling (429);
  - the 4 MB upload limit;
  - an oversized login body gets 413.
- **`test_server.py`.** Legacy-route tests now sign in, because loopback is not an identity. The new `AnonymousAccess` class asserts:
  - 401 for every legacy read, the export, import, inventory and unknown `/api` paths, including the trailing-slash and bare `/api` forms;
  - an old `ara_editor` cookie gets 401;
  - the allowlist answers anonymously;
  - static files stay public.
- **`test_carpetas_migration.ReadOnlyLocal`.** The session is created before read-only mode starts, because an immutable file can't create one. It also asserts that an anonymous GET gets 401 and that login gets 403 in read-only mode.
- **`test_asistente_migracion`.** The backup-order assertion now targets `postgres.LEGACY_TABLES`, and a new assertion checks that `TABLES` begins with the unchanged legacy order.

## Isolated test commands and results (developer-run)

The scratch directory is the session scratchpad. Postgres was a disposable `initdb` cluster on `127.0.0.1:55432`, database `ara_disposable`, user `aratest`, trust auth, no Unix socket. It is stopped after this run.

```sh
# full Python suite, no Postgres (venv 3.14)
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL -u ARA_MAP_TEST_DATABASE_URL ARA_MAP_DB=$TMP/a.sqlite .venv-dev/bin/python3 -m unittest discover -s tests
#   Ran 670 tests — OK (skipped=29: 21 pre-existing + 8 new Postgres tests, all skipped for missing ARA_MAP_TEST_DATABASE_URL)
# same suite on macOS system Python 3.9.6 (verificar.sh compatibility)
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL -u ARA_MAP_TEST_DATABASE_URL ARA_MAP_DB=$TMP/b.sqlite /usr/bin/python3 -m unittest discover -s tests -t .
#   Ran 670 tests — OK (skipped=29)
# full Python suite WITH the disposable Postgres
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL ARA_MAP_TEST_DATABASE_URL=postgresql://aratest@127.0.0.1:55432/ara_disposable ARA_MAP_DB=$TMP/c.sqlite .venv-dev/bin/python3 -m unittest discover -s tests
#   Ran 670 tests — OK (0 skipped; includes tests.test_postgres, tests.test_postgres_aceptacion, tests.test_inventario_postgres)
node --test tests/js/*.test.mjs
#   98 pass, 0 fail (68 at the baseline; the additions are the interface developer's, not mine)
.venv-dev/bin/mypy           # Success: no issues found in 43 source files
.venv-dev/bin/ruff check server api scripts tests
#   4 findings, all pre-existing: api/index.py N801 (Vercel requires the class name `handler`), E402 in scripts/migrate_cloud.py and scripts/setup_cloud.py.
#   `ruff check server tests` (the verificar.sh scope) is clean.
```

Focused new or changed modules (all OK): `tests.test_inventario` 24, `tests.test_inventario_postgres` 8 (with Postgres), `tests.test_cuentas` 6, `tests.test_cloud` 10, `tests.test_server` 23.

Stage 1 exit evidence and where it is tested:

| Evidence | Test |
|---|---|
| New/edit/reopen by three identities with equal capabilities | `EqualTeamAccess.test_three_users_create_edit_and_reopen_each_others_records` |
| Recoverable 409 on conflicting edits | `VersionChecks.test_stale_save_is_a_recoverable_conflict_with_no_partial_change`, plus three-way barrier race `test_simultaneous_saves_of_one_version_have_one_winner` |
| Same on Postgres, separate connections | `test_simultaneous_saves_on_separate_connections_have_one_winner` |
| Real cloud adapter on Postgres | `test_the_cloud_adapter_end_to_end` |
| Actor spoofing rejected | `test_actor_and_server_fields_cannot_be_sent` |
| Rollback on injected failure (create and save) | `test_a_failure_mid_create_leaves_nothing`, `test_a_failure_mid_save_rolls_everything_back` |
| 251-record paging (default 100 and max 250, no gaps or duplicates) | `test_251_records_page_without_gaps_or_duplicates` |
| Mixed and unknown currency filtering | `test_filters_facets_and_mixed_currency` |
| v7 file → v8 upgrade, legacy rows/snapshots byte-equal, single backup, repeat-safe | `SchemaV8.test_v7_file_upgrades_additively_with_a_backup_and_repeats_safely` |
| Postgres schema command on an empty target, run twice | `test_schema_command_creates_and_repeats_on_an_empty_target` |
| Existing v5 workspace → v8 via `migrate_cloud.py --url-env`, run twice, data preserved | `tests.test_postgres_aceptacion` |

## Migration, compatibility and recovery effects

- **SQLite.** Schema v8 is applied automatically the first time new code opens a file. A v7 file gets a `sqlite3.backup` copy in `respaldos/` first, as with earlier upgrades. Legacy tables are not touched.
  - **Important for the owner:** after the upgrade, the local app also requires sign-in, so accounts must be provisioned with `scripts/cuentas.py --sqlite <the app's db>` before anyone can use it. No account exists by default.
  - SQLite backups now strip `team_session` and `team_login_failure`, so a restored copy can't revive sign-ins. They keep `team_user` (password hashes) and private contacts/notes, so restrict where backups are stored.
- **Postgres.** `postgres.TABLES` now includes `team_user` and the four inventory tables (in-database JSON backups). Sessions and login failures are excluded. `ID_TABLES` is unchanged (UUID tables have no identity sequence).
  - There is no restore tool yet; that is B5. Restore order is safe because of the deferred foreign keys.
  - A restore must also revoke sessions. Sessions are excluded from backups, so a full restore of a backup payload already contains none.
- **Read-only mode (`ARA_MAP_READ_ONLY=1`)** can't create sessions on an immutable file. It now serves only the public allowlist and existing valid sessions. This is a supervisor decision: retire the mode or accept it.
- **Stale external material.** `tests/cloud_smoke.py` (a manual live-production smoke script; not part of unittest; not run) and `tests/e2e/smoke.mjs` still use the shared-password flow. README "Publicar en Vercel" still describes the shared password and anonymous browsing. Production environment variable `ARA_MAP_EDIT_PASSWORD` is now unused. All of these need updating at cutover.

## Unresolved issues and untested paths

- **Postgres concurrency limit (§9.5).** Every Postgres session holds the workspace advisory lock, so the Postgres race tests prove the version compare-and-set and idempotency under serialized sessions, not overlapping transactions. The SQLite race tests do overlap (the write lock is the first statement).
- **One request can use two database sessions:** one to resolve the session cookie, one for the handler. On Postgres that means two connections and two advisory-lock acquisitions per authenticated request. Fine for 1–3 users; measure before making load claims.
- **The login throttle is keyed by login only**, so someone can lock a known login for 15 minutes. Add a per-address key if that becomes a problem.
- **The inventory list filters in Python** over a single read of all records. That is correct for hundreds to a few thousand rows; push the filters into SQL beyond that.
- **Unexpected-exception text reaches signed-in callers** through the pre-existing `Error inesperado: …` 500 path. Public routes have no such path today; review this for Stage 2.
- **Not built (later stages):** publish, unpublish, archive, restore, preview, the real public catalog, duplicates, import and adoption, and the restore tool.
- **Not tested:** browser flows (interface and verifier), HTTPS end to end, real Vercel or Neon behavior, and timings for 100 records with three sessions.

## Next dependency

1. The interface developer can wire session, login/logout, inventory list/create/PATCH/history and conflict handling against these DTOs. The public catalog stays empty until Stage 2.
2. Supervisor decisions needed:
   - Read-only mode: retire it or keep it as public-only.
   - Confirm the flat create body.
   - Confirm the additive `confirm` PATCH option.
   - Plan to provision real accounts at cutover. The local app locks everyone out until accounts exist.

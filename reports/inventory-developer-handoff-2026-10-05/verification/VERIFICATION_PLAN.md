# Independent verification plan — ARA Map inventory, Stage 1

Status: Phase A plan. **Phase B (Stage 1) has run since; results are in `../VERIFICATION_RESPONSE.md`.** Original Phase A status, October 5, 2026: preparation only. **No candidate code has been verified.** All `server/`, `api/`, `scripts/`, `web/`, `tests/` files matched `BASELINE_MANIFEST.sha256` when this was prepared; the backend and interface developers are changing them now. Nothing here edits those trees.

## 1. What exists in `verification/`

| Path | Purpose |
|---|---|
| `fixtures/gen_fixtures.py` | Deterministic, stdlib-only fixture generator (seed 20261005). Built-in self-check: counts, publishability per lifecycle, sentinel uniqueness, no sentinel in public fields, determinism. Same hash on Python 3.9.6 and 3.14.5. |
| `fixtures/out/` | `master_120.json`, `matching_251.json`, `users.json`, `sentinels.txt` (2,609 sentinels), `manifest.json` (stable keys, expected blockers/warnings, counts, canonical cases). **Fixture hash `8fa4b0926bcedcded3952c4a1aa68d4fc07882d2c4aad8a896985f9ff388a2b8`.** |
| `baseline_src/` | Frozen copy of the pre-change `server/` + `api/index.py`. All 40 files were hash-checked against the supervisor's manifest before and after the copy (`BASELINE_SUBSET.sha256`, subset hash `632ee386…5e`). It is used only to build legacy fixtures and run positive controls. |
| `legacy/build_legacy_v7.py` | Builds a fictional **schema v7** workspace using the baseline repository functions. It creates 2 folders, 4 bases (one later deleted), 33 terrains with sentinel extras, NULL-currency pre-v7 rows, USD 122.50/m², literal HTML and formula strings, invalid coordinates, 3 saved maps (simple, comparison, and one whose source was deleted), an import format and import records. Its manifest records ids, per-table digests and 174 sentinels. Timestamps are frozen, so the table digests repeat exactly. `--digest DB` recomputes legacy-table digests for migration comparison. |
| `contract_map.json` | **Unfrozen contract details**: private field names, create-body wrapper, provisioning command and any server environment needed for loopback tests. These are filled from `BACKEND_RESPONSE.md` in Phase B, and the file's sha256 is recorded in results. |
| `stage1/aralib.py` | Loopback-only HTTP sessions with per-identity cookie jars. It writes a JSONL evidence log without cookie values or passwords, scans for sentinels in JSON, HTML, headers, cookies and unzipped xlsx files, and manages a restartable server and provisioning with the password sent on stdin. |
| `stage1/serve_target.py` | Runs the candidate's **local** handler (`server.app.Handler`, `ARA_MAP_DB` in a temp directory) or **cloud** handler (`api/index.py`, only against 127.0.0.1:55433) on 127.0.0.1:<port>. It refuses workspace data paths, inherited database URLs and `ARA_MAP_PUBLIC_EDIT`. |
| `stage1/stage1_acceptance.py` | Runs ID-01, ID-02, INV-01, INV-02, INV-03, CON-01 and LEAK, plus an early MIG-02 signal when given `--legacy-db`. It writes `runs/<stamp>-<mode>/{http.jsonl,results.json,route_table.json,server.log}` and exits 1 on any FAIL. |
| `stage1/leak_audit.py` | Runs the §5 anonymous audit. It enumerates the candidate's **live router registry** in a sandboxed subprocess, then adds known-legacy, unknown and path-normalization probes, export bodies and HEAD/OPTIONS/PUT requests. Reads run first and deletes last. It checks exact allowlist shapes, compares 404 bodies for nonpublic IDs and scans static assets. It can run inside the acceptance runner or by itself with `--url`. |
| `harness/pg_disposable.sh` | Creates a throwaway `initdb` cluster in a mktemp directory on 127.0.0.1:55433 with trust auth for the fictional `verifier` role. It exports only `ARA_MAP_TEST_DATABASE_URL` to the child process, removes `DATABASE_URL` and `ARA_MAP_DATABASE_URL`, and tears down on exit. It refuses to start if the port is busy. |
| `runs/control-baseline/` | **Positive control** for the leak detector. It ran against the frozen pre-change loopback server on a copy of the legacy fixture and found 157 FAIL rows and **435 sentinel hits across 36 anonymous responses**, including `/api/bases/:id/terrenos` and `/api/mapas/:id/terrenos`. It also found that anonymous exports return xlsx with status 200 and no sentinels, which confirms the matrix point that sentinel absence alone does not prove safety. The status check catches those exports. This is evidence about the detector, not about the candidate. |

## 2. Fixture content (ACCEPTANCE_MATRIX §3)

- **Master set, 120 records.** `M001`–`M100` are intended to be published as `available`, `M101`–`M110` are drafts, and `M111`–`M120` are intended to be published and then unpublished in Stage 2. Each record uses the contract-v1 draft fields plus logical private fields (`contacts`, `internal_notes`, `extra`, confirmation dates).
- **Currency.** 46 USD, 58 MXN and 16 null currency. 14 records use `price_on_request`. Canonical cases:
  - `M030`: USD 122.50/m², total 1,225,000.00.
  - `M031`: MXN 3,456.78/m².
  - `M032`: USD per-m² only.
  - `M033`: MXN 987,654,321.99.
  - `M040`: deliberate total/unit inconsistency, which should produce a warning without blocking.
- **Area extremes.** `M041` is 1 m² and `M042` is 25,000,000 m².
- **Names and nearby parcels.** `M005`–`M007` repeat a name in different states. `M010` and `M011` are distinct parcels about 45 m apart. `M010` and `M012` form a likely duplicate pair.
- **Literal strings.** `M020`–`M022` contain HTML-like literals and `M023`–`M026` contain formula-like literals. Private extras also contain formula-like text.
- **Confirmation dates.** `M050` is fresh and `M051` is stale. All other records are never confirmed. No staleness cutoff is invented.
- **Drafts.** Missing coordinates (`M101`), swapped X/Y (`M102`), outside Mexico (`M103`), no price (`M104`), unknown availability (`M105`), price-on-request plus an amount (`M106`), an amount without currency (`M107`), missing area (`M108`), zero area (`M109`) and a minimal formula-named record (`M110`). The manifest lists each draft's expected publication blockers under the §5 gate.
- **Matching set, 251 records** (`P001`–`P251`). All are publishable and share one place: Aguascalientes / “Villa Verificación Paginación”, with names “Lote Paginación P###”. Currency split is 100 USD, 126 MXN and 25 price-on-request, and 25 records are `negotiation`.
- **Sentinels.** Each record has its own unique sentinels in its contact, notes, extra keys and values, source filename, commission and private formula. The three users have sentinel usernames, display names (actor metadata) and passwords. A fourth identity, `X`, is never provisioned and is used for signup and enumeration probes. Public fields carry `PUBMARK-<key>` positive markers, never sentinels.

## 3. Matrix IDs by stage

| Stage | Matrix IDs | Phase B coverage |
|---|---|---|
| **1** | ID-01 (create/edit/read part), ID-02, INV-01, INV-02, INV-03, CON-01, §5 legacy-route audit (anonymous denial and sentinel scan) | Scripted HTTP checks in `stage1/` on both adapters. Browser checks for the Stage 1 UI: sign-in, logout/back-navigation clearing, editor conflict recovery and the phone filter drawer. |
| 2 | PUB-01, PUB-02, PUB-03, CON-02, PRE-01, VIEW-03, ID-01 publish/unpublish/archive parts, §5 public allowlist shape and catalog 404 equality | Lifecycle routes are probed now and reported as SKIP when absent. The public-shape checks already exist in `leak_audit.py` and switch on when `/api/publico/terrenos` exists. |
| 3 | IMP-01, DUP-01, ATT-01, ID-01 import part, MIG-01 adoption part | Requires the >100-row multi-sheet workbook with >12 exclusions, which is not generated yet. |
| 4 | CON-03, VIEW-01, VIEW-02, REG-01, REG-02, MIG-01–MIG-05, 100+ records with three sessions, performance diagnostics | Final acceptance. |

## 4. Phase B commands (Stage 1)

These are run from `verification/` after `BACKEND_RESPONSE.md` and `FRONTEND_RESPONSE.md` exist. First, record the candidate manifest:

```sh
cd "/Users/andrejasso/Desktop/ARA Map"
find server api scripts web tests -type f ! -path '*/node_modules*' ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 shasum -a 256 > reports/inventory-developer-handoff-2026-10-05/verification/runs/CANDIDATE_MANIFEST.sha256
shasum -a 256 -c reports/inventory-developer-handoff-2026-10-05/BASELINE_MANIFEST.sha256 | grep -v ': OK$'   # changed-file list
```

Next, fill in `contract_map.json` from `BACKEND_RESPONSE.md`: field names, `provision_cmd` (password on stdin) and loopback cookie environment. Then:

```sh
V="reports/inventory-developer-handoff-2026-10-05/verification"; PY=.venv-dev/bin/python3
$PY $V/fixtures/gen_fixtures.py --check                                    # hash must equal 8fa4b092…a2b8
T=$(mktemp -d); $PY $V/legacy/build_legacy_v7.py --out "$T/legacy_v7.db"

# 1. Local adapter, fresh disposable SQLite
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL -u ARA_MAP_TEST_DATABASE_URL \
  $PY $V/stage1/stage1_acceptance.py --mode local --port 8433
# 2. Local adapter over a copy of the legacy v7 workspace (upgrade + legacy leak audit + MIG-02(pre))
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL -u ARA_MAP_TEST_DATABASE_URL \
  $PY $V/stage1/stage1_acceptance.py --mode local --port 8433 --legacy-db "$T/legacy_v7.db"
# 3. Cloud adapter (api/index.py) against the disposable cluster. First initialize its schema with the
#    backend's explicit-target migration command (contract: no schema changes on ordinary cloud requests).
$V/harness/pg_disposable.sh -- sh -c '<backend migrate cmd using ARA_MAP_TEST_DATABASE_URL> && \
  '"$PY $V/stage1/stage1_acceptance.py --mode cloud --port 8433"
# 4. Existing project suites, isolated (record skips separately)
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL -u ARA_MAP_TEST_DATABASE_URL ARA_MAP_DB="$T/suite.db" \
  $PY -m unittest discover -s tests -v
node --test tests/js/*.test.mjs
$V/harness/pg_disposable.sh -- $PY -m unittest tests.test_postgres tests.test_postgres_aceptacion -v
# 5. Re-run 1 with --public-edit-env (server gets ARA_MAP_PUBLIC_EDIT=1):
#    anonymous must still be denied (contract: the bypass must not open inventory).
```

**Browser (Stage 1 UI).** Use playwright-core from `tests/e2e/node_modules` with the installed Chrome or Chromium, against `http://127.0.0.1:8433` only. Viewports are 1440×900, 1024×768 and 768×1024 (tablet), 390×844 (FRONTEND_PACKET) and 375×812 (matrix VIEW-01); the 960 px breakpoint is checked at 959 and 961 px. There are four contexts: users A, B and C plus anonymous. Each run captures screenshots, console and network logs, and a DOM/localStorage/sessionStorage sentinel scan after logout and Back navigation. This browser script will be written in Phase B against the real UI, because selectors cannot be known before then.

## 5. Environment requirements

- Python 3.14.5 in `.venv-dev`, which has psycopg 3.3.6 and openpyxl 3.1.5. `/usr/bin/python3` 3.9.6 also runs the generators.
- PostgreSQL 17.11 binaries in `/opt/homebrew/bin` (the harness is proven: initdb, start, UTF8 database, teardown).
- Node, `tests/e2e/node_modules/playwright-core`, Chrome and a Playwright Chromium cache.
- Ports: 8433 for the app and 55433 for Postgres. Both were free and are released after each run.
- Rules: never `.env.local`, never `scripts/migrate_cloud.py` or `setup_cloud.py` in default mode, never the default `datos/` or `api/data/` database, never a non-loopback URL. `serve_target.py`, `aralib.Session` and `build_legacy_v7.py` enforce these rules in code.

## 6. Ambiguities and cases untestable as written. Supervisor decision requested where marked

1. **VIEW-01 phone size.** The matrix uses 375×812 and FRONTEND_PACKET uses 390×844. Both will be covered.
2. **Unfrozen field names.** The names of private draft fields (contacts, internal notes, extras, price and availability confirmation dates) and the create-body shape (flat or `{draft:…}`) are not frozen. Handled in `contract_map.json`. A wrong mapping shows up as an INV-01 round-trip FAIL, not as a silent pass.
3. **Provisioning interface.** The contract does not specify it. The runner needs a non-interactive command that reads the password from stdin.
4. **Invalid coordinates in drafts.** *Decision:* BACKEND_PACKET says “reject … invalid coordinate pairs”. The matrix §3 and §5 say drafts may hold invalid or missing coordinates and that coordinates are a *publication* blocker. My scripts record a draft rejected at save as WARN, not FAIL. Which rule applies?
5. **Unknown `/api/*` routes, anonymous.** *Decision:* The audit expects 401 (deny before fallback) and records a non-leaking 404/405 as WARN. Should 404 be acceptable?
6. **Legacy-route closure at Stage 1.** *Decision:* INTEGRATION_DECISIONS §1 says Stage 1 *can* close the old public routes, while START_HERE puts legacy-route closure in the Stage 2 exit. Is the §5 audit a **Stage 1 gate** or informational at Stage 1? The scripts run it either way. The positive control shows that today's local adapter leaks.
7. **Mutations without an Origin header.** A mutation with a valid cookie and no Origin (curl, not a browser) is not specified. Cross-site browser requests always send Origin, so the scripts test evil, `null` and lookalike origins.
8. **Expired sessions.** The contract has no TTL knob. The runner expires sessions by updating the disposable database (a `*session*` table with `*expir*` and `*user*` columns). If the schema differs, the result is SKIP with a reason. A backend-documented test TTL would be better.
9. **Fault injection (INV-02 and INV-03 rolled-back transactions, durable result committed with the write).** This cannot be reached over HTTP. Options: the backend's repository tests, plus my table-count invariants (already scripted), plus, if accepted, a verifier-owned wrapper in `serve_target.py` that monkeypatches a repository call to raise mid-transaction. That wrapper changes only my process, not their files. *Decision:* is that wrapper acceptable as independent evidence?
10. **Unspecified login and session details.** Rate-limit thresholds and lockout scope are unspecified, so the probe runs last and its result is INFO. A per-IP lockout would affect every loopback user. The scope of idempotency keys across users and of logout across a user's other sessions is also unspecified (both INFO).
11. **CON-01 on Postgres.** Postgres takes a workspace-wide advisory lock per request (BACKEND_PACKET). The 3-way barrier race will serialize, so it proves version checking, not interleaving inside a transaction. True separate-connection interleaving inside the repository needs a direct repository harness in Phase B.
12. **Publication cases.** “Import, publish, unpublish, archive” in ID-01 and “four browser contexts” in PUB-01 belong to Stage 2 or 3. Stage 1 reports them as SKIP when the routes are absent.
13. **Stage 3 workbook.** The matrix §3 workbook (>100 rows, multiple sheets, >12 exclusions) and the genuine-duplicate legacy versions are Stage 3. Not generated yet.
14. **Performance.** Thresholds in matrix §8 are diagnostic only. Create, read and patch latency p50/p95 is recorded per run with the environment (loopback, single machine, disposable database). That is not a capacity claim.

## 7. Not done in Phase A

No acceptance run against the candidate. No `VERIFICATION_RESPONSE.md`. No browser script yet, because it needs the real UI. No Stage 2–4 scripts beyond the public-shape checks already present in the leak audit.

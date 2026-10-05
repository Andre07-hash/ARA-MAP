# Verification response: Stage 1 (independent)

October 5, 2026. Independent verifier. This covers Stage 1 only: the API on both adapters and the integrated browser pass. **It is not a release recommendation.** Stages 2–4, the migration/recovery rehearsal (MIG-01, MIG-03 to MIG-05) and all live/production checks are out of scope and unverified. Final readiness requires the supervisor's integrated review and a reviewed release runbook.

## Verdict for Stage 1

**Stage 1 is accepted on local disposable evidence. There are no blocking defects.**

- The server rejects anonymous `/api/inventario/*` with 0 bypasses across 357 inventory probe rows per run. 355 return 401; the 2 non-API spellings `/./api/inventario/terrenos` and `/api%2finventario%2fterrenos` return the static HTML app shell and no data. Stage 1 blocking cases ID-01, ID-02, INV-01, INV-02, INV-03 and CON-01 pass on SQLite and on disposable Postgres through the cloud adapter.
- The legacy-route anonymous audit found **0 sentinel hits and 0 non-401 responses** on both engines, including over a fictional schema-v7 workspace. That gate becomes blocking at Stage 2 exit.
- v7→v8 left every legacy table byte-identical on both engines, both right after the upgrade and at the end of each run.
- The integrated browser pass passed every Stage 1 scenario except one low-severity accessibility defect (D-1).
- The developers' own tests were **not** used as evidence. I wrote and ran my own HTTP and browser scripts.

| Matrix ID / scope | SQLite (local adapter) | Postgres 17.11 (cloud adapter `api/index.py`) | Browser (Chromium 153, local adapter) |
|---|---|---|---|
| ID-01 equal powers, actor from session | PASS | PASS | PASS (A creates, B edits A's record, C recovers from a conflict; history names all three) |
| ID-02 auth negatives, logout, no leakage | PASS | PASS | PASS (deep link, generic error, HttpOnly + Strict cookie, logout + late response + Back) |
| INV-01 create/edit/reopen, restart persistence | PASS (1 WARN, O-1) | PASS (1 WARN, O-1) | PASS |
| INV-02 history, validation, unknowns, rollback | PASS (with verifier fault injection) | PASS (with verifier fault injection) | PASS (history panel) |
| INV-03 idempotency, incl. concurrency and restart | PASS | PASS | n/a |
| CON-01 stale 409, no partial write, 3-way race | PASS | PASS (serialized, see O-4) | PASS (conflict review, deliberate resave) |
| §5 anonymous route audit (594 probes per run) | PASS: 0 hits | PASS: 0 hits | PASS: anonymous startup calls only config, session and publico |
| MIG-02 early check (v7→v8 legacy byte-equality) | PASS | PASS | n/a |
| VIEW-01/02 Stage 1 parts (widths, drawer, keyboard) | n/a | n/a | PASS, 1 WARN (D-1) |
| VIEW-03 assembly (251 matching + 369/370 full list) | n/a | n/a | PASS (2 pages of 250+1; table, legend, map markers and count all show 251) |
| REG-01 legacy bases/maps reachable signed in | backend: authenticated reads 200 and export 200 | same | PASS (v7 base and frozen saved map reopen) |
| Public catalog with records, PUB-*, PRE-01, CON-02 | **N/A, Stage 2** | **N/A** | **N/A** (only the empty state was checked) |
| IMP-01, DUP-01, ATT-01, MIG-01/03/04/05, CON-03, REG-02 | not run (later stages) | not run | not run |

## Defects (owner, severity, repro, evidence)

**D-1. Interface, LOW (accessibility, WCAG 2.4.3): focus is lost after closing the Historial dialog with the keyboard.**

- Route/action: signed-in `#/inventario/<id>`. Tab to `Historial`, press Enter to open the dialog, press Escape.
- Expected: focus returns to the `Historial` trigger.
- Actual: `document.activeElement` is `BODY`, so a keyboard user restarts from the top of the page.
- Smallest repro: any signed-in record detail, using the three steps above.
- Evidence: `verification/runs/20261005-151015-browser/browser_results.json`, check `keyboard: focus returns to the Historial trigger after Escape` (WARN).
- Not release-blocking at Stage 1. The Filtros drawer does return focus correctly.

There are no other defects. During the run I found and fixed six problems in my own test scripts; these were not candidate defects:

- M102 stores a swapped X/Y pair, so |lat| > 90. INTEGRATION_DECISIONS §9.1 correctly requires a 422 for that.
- My field mapper dropped `extra` before sending, so I sent the raw key. The server then returned 422 correctly.
- The token-in-body scan included the `Set-Cookie` header.
- I treated `/./api/…` and `/api%2f…` as API paths. The server serves the static shell for them: HTML, no data.
- A canvas-rendered map needed instrumentation to count markers.
- My first late-response test delayed the request rather than the data response. It now holds a real 200 response containing private data until after logout.

The scripts still in place enforce the stricter versions of these checks.

## Observations and limitations (not defects; supervisor decisions)

- **O-1. Backend deviation 5 is pending confirmation.** A typed price with no currency gets a 422 on save (fixture M107). Contract §5 says drafts may be incomplete, while the existing manual-entry rule says a typed price needs a currency. Recorded as WARN and not counted as a defect.
- **O-2. Stage 2 placeholder.** `GET /api/publico/terrenos?campos=contacto&include_private=1` returns 200 with an empty envelope. Contract §6 requires 422 for unknown or private selectors. It must be fixed in Stage 2 and is re-tested automatically (WARN).
- **O-3. `Idempotency-Key` is global, not per user.** B replaying A's key with the same body gets A's original result (200, same ID). With equal powers this reveals nothing B could not already read. Confirm that this scope is intended.
- **O-4. Postgres concurrency is a stated limitation** (§9.5). The workspace advisory lock serializes requests, so the Postgres 3-way race and the concurrent same-key create prove compare-and-set and idempotency, not overlapping transactions.
- **O-5. Signed-in 500 responses expose raw exception text** (`"Error inesperado: <exception>"`) and have no `detalle.code`. The backend already listed this; it is seen in the FAULT runs. It never appeared anonymously. Review it before Stage 2.
- **O-6. Logout scope.** Logout revokes only the current session; the same user's other sessions stay valid. That matches the contract ("revoke current session"). Password reset and deactivation do end all of that user's sessions, which was verified.
- **O-7. Login throttle.** The limit is 5 failures per login per 15 minutes (429). Other accounts can still sign in from the same address. Lockout of a known login is possible, as the backend noted.

## What was exercised (highlights)

**ID-02**

- Wrong password and unknown user give an identical 401. Failed logins set no cookie.
- Random and tampered `ara_sesion` cookies are rejected.
- An old `ara_editor` shared-password cookie, correctly HMAC-signed with a known password that the server was given, grants nothing.
- `ARA_MAP_PUBLIC_EDIT=1` grants nothing (a dedicated run).
- Evil, `null` and look-alike `Origin` values get 403 on PATCH, create and login, and nothing is written.
- No signup on 8 candidate paths, anonymous or signed in.
- After logout, a copied cookie gets 401 on both read and write. Logout is idempotent.
- An expired session gets 401: I set `team_session.expires_at` in the disposable database, as allowed by §9.6.
- Password reset and deactivation through `scripts/cuentas.py` end existing sessions.
- No password, hash material or session token appears in any response body or in the server/provisioning logs.
- No `Access-Control-Allow-Origin` header on any response.

**INV-01**

- All 118 saveable master fixtures round-trip exactly, including accented names, USD 122.50 and MXN 3,456.78 cents, HTML-like and formula-like literals, nulls, and sentinels in `contacto`/`notas_internas`.
- Outside-Mexico and missing coordinates save, and the record shows a `location_invalid` blocker.
- Values and versions are identical after a server restart.

**INV-02**

- 13 invalid edits each get a 422 with `detalle.code`, and nothing changes (version, draft, history, row counts). The invalid edits were: nonnumeric text, `NaN`/`Infinity`, an unknown currency or availability, `extra`, an unknown field, |lat| > 90, |lon| > 180, negative area, an over-long contact, and non-boolean `price_on_request`.
- History records before/after values with the actor and time.

**Fault injection** (INTEGRATION_DECISIONS §9.4, my wrapper process only).

- **The only patch:** `server.repo.inventario._event` is wrapped so it raises when the event details contain a unique marker. That makes the history insert fail after the terrain, revision and pointer writes.
- Create: 500, no rows in any inventory, team or idempotency table, and the key stays free.
- Save: 500, and version, pointer, history and counts are unchanged. A later save with the same `expected_version` succeeds.
- No candidate file was modified.

**INV-03**

- A missing or empty key gets 422 and nothing is created.
- The same key and body returns the identical result, including after a restart.
- The same key with a different body gets 409.
- 5 concurrent same-key creates produce 1 record.

**CON-01**

- Tested for the same field, for different fields and for private note vs. public field. Each time: 409 `conflict`, no partial write, history +1 only, and a deliberate resave succeeds.
- `expected_version` that is greater than current, null or a string is refused.
- 3 sessions racing on the same version: exactly one 200 and two 409s, and the winner's value persists.

**§5 audit**

- The final router registry (41 routes, enumerated from the live code) was probed with legacy IDs, 26 inventory UUIDs and a random UUID, 10 export bodies, unknown and path-trick URLs, inventory path tricks and HEAD/OPTIONS/PUT.
- Every non-allowlisted anonymous request got exactly 401. `GET /api/session` returned exactly `{authenticated:false}`.
- Signed-in unknown routes get 404. Non-public detail 404 bodies cannot be told apart.
- Signed-in legacy export still returns an xlsx, and legacy reads get 401 after logout.
- Static assets carry 0 sentinels.
- **Positive control:** the same audit against the frozen pre-change server found 435 sentinel hits. The detector works.

**Browser**

- Anonymous startup calls only `GET /api/config`, `/api/session` and `/api/publico/terrenos`, with no 401s and no sentinel in DOM, inputs, local/session storage, URL, title or caches.
- No horizontal overflow on the catalog, inventory or editor at 1440×900, 1024×768, 768×1024, 390×844, 375×812, 959×900 and 961×900.
- The breakpoint behaves as specified: at 959 the drawer button shows and the rail is hidden; at 961 the reverse.
- Phone, at both 390 and 375: the Filtros drawer filters on the server and keeps its state when reopened, Escape closes it, and focus returns to the trigger. A result can be selected and its detail read. `Guardar borrador` stays inside the viewport and saving works.
- Keyboard only: sign in → Editar → change Dirección → Guardar → Historial → Escape → drawer → Cerrar sesión.
- A late 200 response with private data, delivered 3 s after logout, renders nothing. Back ×2 and revisiting the private URL show only the sign-in dialog.
- The `alert()` trap caught nothing, and HTML-like names render literally.

## Commands (exact) and environment

Run from `/Users/andrejasso/Desktop/ARA Map` with `V=reports/inventory-developer-handoff-2026-10-05/verification`:

```sh
# API, SQLite: fresh / over the legacy v7 workspace / with ARA_MAP_PUBLIC_EDIT=1
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL -u ARA_MAP_TEST_DATABASE_URL .venv-dev/bin/python3 $V/stage1/stage1_acceptance.py --mode local --port 8433
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL -u ARA_MAP_TEST_DATABASE_URL .venv-dev/bin/python3 $V/stage1/stage1_acceptance.py --mode local --port 8433 --legacy
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL -u ARA_MAP_TEST_DATABASE_URL .venv-dev/bin/python3 $V/stage1/stage1_acceptance.py --mode local --port 8433 --public-edit-env
# API, Postgres through the cloud adapter (the schema is set up by scripts/esquema.py --url-env, twice, then --check)
$V/harness/pg_disposable.sh -- .venv-dev/bin/python3 $V/stage1/stage1_acceptance.py --mode cloud --port 8433
$V/harness/pg_disposable.sh -- .venv-dev/bin/python3 $V/stage1/stage1_acceptance.py --mode cloud --port 8433 --legacy
# Integrated browser pass (local adapter over a v7 workspace copy, 371 fixtures seeded via the API)
env -u DATABASE_URL -u ARA_MAP_DATABASE_URL -u ARA_MAP_TEST_DATABASE_URL .venv-dev/bin/python3 $V/browser/run_browser.py
# Project suites, as context only (developer-owned)
$V/harness/pg_disposable.sh -- env ARA_MAP_DB=<tmp>/suite.db .venv-dev/bin/python3 -m unittest discover -s tests   # 670 OK, 0 skipped
node --test tests/js/*.test.mjs                                                                                    # 98 pass, 0 fail
```

**Environment:**

- Machine: Apple M3, macOS 26.6.
- Runtimes: Python 3.14.5 (`.venv-dev`, psycopg 3.3.6); PostgreSQL 17.11 (throwaway `initdb` cluster on 127.0.0.1:55433, trust auth, torn down after each run); Node 23.7.0.
- Browser: playwright-core 1.63.0 with Chromium 153.0.8010.12 headless. Map tiles were stubbed.
- App: 127.0.0.1:8433, with SQLite in a fresh `mktemp` directory each run.
- Rules followed: no `.env.local`, no default database, no `migrate_cloud.py`/`setup_cloud.py`, no production URL.
- Test data: fictional fixtures with hash `8fa4b0926bcedcded3952c4a1aa68d4fc07882d2c4aad8a896985f9ff388a2b8`. `contract_map.json` sha256 is `f3593dbdf5d09af6e65d3f741f6a69f47ac1510ebf35d569ca73c848f1ac6f5a`, filled from BACKEND_RESPONSE.md.

## Source manifest at test time

- `verification/runs/CANDIDATE_MANIFEST_stage1_final.sha256` covers 113 files under `server/ api/ scripts/ web/`. The manifest file's own sha256 is `381b36d547d0a2579283889c022d6bac162740b252f4bf6dda01c1d09784eed1`.
- `server/ api/ scripts/` are byte-identical to `CANDIDATE_MANIFEST_stage1_api.sha256`, which was taken before the API runs at 14:56. All 12 backend files listed in BACKEND_RESPONSE.md match their stated hashes, and the `web/` files I spot-checked match FRONTEND_RESPONSE.md.
- My tooling is listed in `verification/VERIFIER_TOOLS.sha256`.

## Evidence locations (`verification/runs/`)

| Run | Engine / variant | Result |
|---|---|---|
| `20261005-150300-local` | SQLite fresh | 757 PASS / 0 FAIL / 2 WARN / 5 SKIP |
| `20261005-150311-local` | SQLite + legacy v7 | 760 / 0 / 2 / 5 |
| `20261005-150322-local` | SQLite, `ARA_MAP_PUBLIC_EDIT=1` | 757 / 0 / 2 / 5 |
| `20261005-150334-cloud` | Postgres, cloud adapter | 757 / 0 / 2 / 5 |
| `20261005-150349-cloud` | Postgres + legacy v7 | 760 / 0 / 2 / 5 |
| `20261005-151015-browser` | Integrated browser | 90 PASS / 0 FAIL / 1 WARN (D-1) / 1 N/A, with 34 screenshots in `shots/` |
| `control-baseline` | Pre-change server, positive control | 435 hits (expected) |

Each API run directory holds `results.json`, `http.jsonl` (cookie values are never logged; passwords redacted), `route_table.json` (per-probe anonymous status, hits and signed-in status), `server.log` and `provision.log`. The 5 SKIPs are lifecycle routes absent until Stage 2 and the source-lineage check (Stage 3).

## Performance observations (diagnostic only, not capacity claims)

All numbers come from one machine, over loopback, with a disposable database, at fewer than 400 records and a few seconds of serial requests.

- **API latency p50/p95:**

  | Operation | SQLite (ms) | Postgres via cloud adapter (ms) |
  |---|---|---|
  | create | 2.9 / 5.6 | 6.4 / 7.6 |
  | patch | 2.8 / 8.3 | 7.0 / 12.4 |
  | get | 2.4 / 3.0 | 5.0 / 5.7 |

- **Browser, warm, SQLite:** assembling 370 records to the count took about 130 ms after reload. The 251-record search took about 840 ms from typing, which includes the 250 ms debounce. A UI create took about 40 ms server round trip.
- **Not measured:** cold start, real network, Vercel/Neon, map-tile latency, Lighthouse, Firefox/Safari, or any load from public visitors.

## Unverified (honest gaps)

- Everything in Stage 2+: publish/preview/public catalog with records, CON-02, PRE-01, PUB-*, import/adoption/duplicates/attention, MIG-01/03/04/05 (restore tooling does not exist yet), CON-03 with a mid-flow process restart under three browser sessions, and REG-02 export round-trip in the browser.
- **Production cookie `Secure` behavior.** The `Secure` attribute was observed on the cloud adapter over HTTP, but HTTPS end to end was not tested.
- Real Vercel/Neon, multi-worker throttling, Firefox/Safari, axe/Lighthouse, screen readers.
- Overlapping Postgres transactions (O-4).
- The legacy anonymous audit becomes a **blocking** gate only at Stage 2 exit. Today's PASS must be re-run on the Stage 2 candidate.

## Next

1. Interface fixes D-1.
2. Supervisor decides O-1 and O-3.
3. Backend addresses O-2 and O-5 in Stage 2.

The same scripts re-run unchanged on the Stage 2 candidate: `stage1_acceptance.py`, `leak_audit.py` with its public-shape checks, and `run_browser.py`. Stage 2 cases (PUB/PRE/CON-02) still need to be added.

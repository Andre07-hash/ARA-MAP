# Team A — F0-A: free hosted pilot and early integration

You are Team A for `Andre07-hash/ARA-MAP`. Implement this packet now. The owner requires a $0 private pilot for 50–100 terrains, no payment method and no billing exposure. Read `reports/free-private-pilot-2026-10-12/START_HERE.md` at the exact supervisor commit relayed by the owner. It supersedes the earlier Vercel/AWS transfer packet. No additional general planning/readiness report is requested.

Target: existing frontend and Python backend together on Render Free; Neon Free retains application data/geometry/auth; Supabase Free private Storage retains PDF/KMZ bytes. Keep full 20 MiB KMZ / 25 MiB PDF whole-file workflows. Supabase's 1 GB total quota is a real constraint; the initial operator budget is 700 MB for all final files/history, with remaining space for staging/tests. This is not a promise that 100 maximum-sized KMZ/PDF pairs fit. Disclose idle wake/suspension limits and prove the real files fit before client import.

## Start and parallelize

Start `codex/team-a-free-pilot-v1` from `4670df7348265af66c640069e5ece2a274830fa3`. If you already have M1 work, preserve it on its branch and reuse relevant commits deliberately; report the delta. Preserve old #29, #28, #30 and C1. No force push.

Use up to three agents concurrently if available within your current allowance:

1. **Host agent:** new Render startup/adapter, configuration, packaging and focused HTTP/security tests.
2. **Pilot journey agent:** synthetic 50/100-record loading into the actual editable master table, permissions and onboarding checks. Own test fixtures/journeys; request any application fix from the lead so it does not overlap host/B files.
3. **Operator agent:** minimal Spanish onboarding, fresh-target setup, consistent DB backup/restore and free-quota/cold-start runbook. Own documentation and isolated operator-test files.

You are the integrator/reviewer. Give agents explicit file ownership and isolated worktrees if needed. Do not have multiple agents edit a shared file. No paid agent capacity, extra Claude account or unapproved services.

## Implement while B works

- Add a small hosted entry point (for example `server/hosted.py`) reusing the accepted router/services. Serve web assets and APIs from the same origin. Bind to Render's `0.0.0.0:$PORT`, use supported pinned Python, require Postgres and refuse SQLite fallback. Local launch remains loopback-only and dependency-free. Do not simply expose the development launcher to the internet or rewrite the app in a new framework.
- Preserve authentication, capability/scope checks, read-only mode, Secure/HttpOnly/SameSite cookies, safe binary/no-store headers and origin protection. Define the external host/origin explicitly; forwarded headers must not let a client choose a trusted origin. Test through a local proxy-shaped request path.
- Preserve the existing bounded whole-file body reader and 25 MiB application ceiling, including exact 20/25 MiB cases, malformed length, incomplete body and oversized refusal. Do not inherit the Vercel adapter's 4 MiB cap or send transfers through a Vercel Function. Keep metadata limits. Use bounded request concurrency/timeouts appropriate to the small host; no durable work in process memory and no new queue system.
- Prepare a reviewed Render config with Free plan, manual deployment, health check and server-only secret placeholders. Disable automatic deployment in the intended setup; do not activate resources. Preserve existing Vercel settings without deploying them. No persistent local disk is assumed.
- Wire B's `server/almacen_supabase.py:fabrica_desde_entorno(environ)` into `api_archivos.configurar_almacen`. Shared variables are `ARA_MAP_ARCHIVOS_SUPABASE_URL`, `ARA_MAP_ARCHIVOS_SUPABASE_KEY`, `ARA_MAP_ARCHIVOS_SUPABASE_BUCKET`. Factory construction is pure. Use injected existing local/fake stores only in test scaffolding while B is working; do not build a competing provider adapter or commit a fake production implementation.
- You own dependency declarations and exact hosted pins. Obtain B's tested official SDK version, preserve local Python 3.9 compatibility by lazy/optional hosted dependencies, and use a supported Python for hosted execution. Never print secrets.
- Prove the import/load path for 50–100 rows ends in the editable master table with the correct base and grants. Use a synthetic spreadsheet through the intended user flow. If only legacy import exists, implement the smallest reviewed bridge or operator import using existing validated services, with dry-run and duplicate handling. No new mapping product, direct uncontrolled SQL bulk load or real data. You own this bounded gap if it exists.

## Integrate early

Create an early draft PR targeting `claude/team-a/application-integration` after required checks. Ask the owner to relay B's first fetchable adapter SHA as soon as it is usable; do not wait for B's finished report or all recovery tests.

On each relayed B SHA, inspect the exact delta, interface and focused results. Check authorization before storage resolution and provider I/O outside DB write locks. Merge it ordinarily into your new branch only after this focused review. Label early integration provisional. Integrate accepted batching `bc7e421e5f2a94bdaa6a61ca14fc8c41e381f9c3` once if not already an ancestor. Do not remerge #28, rewrite B's history, or modify old PRs. Later B handbacks are additive merges. Resolve B-owned defects with a precise owner-relayed reproducer; do not create a second implementation on B's branch.

## Verify and prepare handover

Run affected host/security and synthetic loading tests while B develops. After integration, run the combined private user journey on SQLite/disposable Postgres as applicable, full-size upload/download, revoked/archived scope, unavailable storage and a true restart using the same external DB/store substitute. Run normal required checks/CI before push. Reuse unchanged parser, renderer and large-dataset evidence.

Finish a short operator checklist for Free-only accounts with no card, isolated schema, managed users/grants, manual deploy, provider usage, and cold wake. Build consistent logical DB backup/restore instructions that consume B's immutable-file manifest/export; verify all master/attachment/geometry/history tables are covered. Exclude/reset sessions, login failures and processing leases on an isolated restore. Never assume a provider database backup contains file bytes.

Return the first working host commit early, then a combined candidate with exact SHAs, B/#30 ancestry, draft PR, exact-head CI and concise evidence. Distinguish local readiness from hosted acceptance. The next operator release must prove full-size transfers, provider collision behavior, permissions, cold wake/redeploy and one restore with disposable data before real client use. List only the exact resources/access steps still needed.

Authorized: local implementation, isolated test dependencies, synthetic tests, new branch pushes/draft PR and local candidate merges. Stop before provisioning, enabling any billing, accounts/secrets changes, deployment, real imports or GitHub PR/main merge. Finish independent work instead of waiting for those operations. Team B is a separate Claude session on another computer/account; the owner relays published commits and handbacks. Never assume shared local state.

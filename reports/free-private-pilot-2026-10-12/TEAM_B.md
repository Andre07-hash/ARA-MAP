# Team B — F0-B: simple private Storage adapter and recoverable files

You are Team B for `Andre07-hash/ARA-MAP`. Implement now for a $0 private pilot with 50–100 terrains, no payment method and no billing exposure. Read `reports/free-private-pilot-2026-10-12/START_HERE.md` at the exact supervisor commit relayed by the owner. This supersedes the Vercel/AWS chunk/OIDC implementation packet. No further provider survey or general design report is requested.

Target: Supabase Free **private Storage** for bytes, the existing Python app on Render Free, existing Neon Postgres for all application data/auth/geometry. Keep the existing whole-file routes/client and 20 MiB KMZ / 25 MiB PDF. No browser storage credentials, chunk/slice protocol, composition API, AWS STS/OIDC, custom signer, Supabase Auth/database migration or new schema by default.

## Start and parallelize

Start `codex/team-b-free-files-v1` from `4670df7348265af66c640069e5ece2a274830fa3`. Preserve #28, #30 and A's branches. If you have unpublished M1 implementation, preserve it and reuse relevant bounded store/error tests; do not finish superseded work. No force push.

Use up to three agents concurrently within your current allowance:

1. **Adapter agent:** `server/almacen_supabase.py`, official SDK integration and backend contract tests.
2. **Lifecycle agent:** narrowly necessary `server/archivos.py` / `server/api/archivos.py` fixes and focused scope, error, deadline, collision/uncertain-write tests. No provider adapter edits.
3. **Recovery agent:** read-only inventory/integrity/export tooling, manifest and synthetic restore checks. No application/lifecycle edits.

You integrate/review their work. Give each agent the same pin and shared contract, separate files/worktrees and exact expected tests. Do not purchase agent capacity. Send interface details between your own agents immediately; A's separate session receives them through the owner.

## Build the first usable slice

Implement the existing six-method `Almacen` contract. Public factory: `fabrica_desde_entorno(environ) -> FabricaAlmacen | None`, pure construction without provider calls. Configuration: `ARA_MAP_ARCHIVOS_SUPABASE_URL`, `ARA_MAP_ARCHIVOS_SUPABASE_KEY`, `ARA_MAP_ARCHIVOS_SUPABASE_BUCKET`. Use a server-only secret/service credential for a dedicated private storage project; no browser exposure. A owns package declarations, host setup and secret wiring. Give A the exact official SDK version tested in your isolated environment; lazy import preserves SDK-free local startup.

- `guardar_temporal`: bounded validated input, atomic whole-object staging replacement; input/size failure preserves the old staging object. Disposable spooling is allowed, never authoritative local storage.
- `copiar`: snapshot bounded source bytes and create the fresh final key with the provider's documented no-upsert upload. No HEAD-then-overwrite, no replacement of a final object. Map a real duplicate-object condition to `ColisionError`; prove concurrent one-winner behavior. Do not map every 400 as a collision.
- `leer`: preserve bounded reads and reject oversized objects before exposing bytes; avoid an unbounded convenience SDK download. `tamano_de`, `borrar`, `listar`: preserve existing results, exact-key deletion and lazy pagination. Validate keys using accepted rules.
- Prevent stale staging reads after replacement: private authenticated/no-cache access and overwrite→immediate-read/completion tests. If SDK behavior cannot enforce the contract, use documented bounded HTTP transport narrowly, and report it. Do not invent unsupported methods or hand-roll signing.

Create an early new draft PR targeting `claude/team-a/application-integration` after required checks. Publish **adapter + factory + contract tests first**; relay exact SHA, SDK pin and configuration/interface note while other agents continue. Do not wait for the final report. This is provisional integration input, not accepted hosted behavior. Further work uses additive commits on the same branch.

## Preserve lifecycle and privacy

Make only the service/API changes needed for remote failure handling and safe injection. Resolve session/capability/current resource scope/pending ownership before failing storage resolution or provider calls. Do not insert a new pending row when configuration is missing; retain replay semantics. Do not break unrelated metadata/geometry routes when the store is unavailable. No provider I/O under DB write locks.

Preserve upload/completion deadlines, lease, pending limit, idempotency, cancellation, final size/SHA/signature checks, explicit candidate selection/activation, revision conflicts, scope-loss rechecks and the old active boundary after invalid replacement. Downloads remain fully verified whole-file responses with safe private headers. Do not change frontend upload/download protocol.

Track a final write attempt before provider I/O; lost responses may leave an object. Cleanup only the attempt's nonce after reliable DB proof it is unreferenced; retain on doubt and report cleanup pending. Never delete the collision winner. Use a new nonce on application retry. Test provider failure before/after write, failed DB reference check and a restart between write/commit. Preserve existing final/history bytes.

Map missing config to safe file 503, transient failures to retryable storage failure and provider access denial to a nonretryable storage failure. Quota/paused-provider errors must not silently discard pending or accepted data or look like app authorization errors. Sanitize logs. Check the current provider docs and exact SDK error behavior while implementing.

## Recovery and small-pilot capacity

Supabase Free provides 1 GB total Storage, so record count is not capacity. Initial operator budget: 700 MB decimal of all retained final files/history; staging, tests and uncertain/unreferenced objects also consume quota. Keep full per-file limits. Do not auto-delete history, add billing or build a complex new quota service. Report actual totals through the inventory tool and expose useful provider-quota failure. A will check the real intended file batch before client import.

Implement or extend a read-only verifier/exporter (for example `scripts/verificar_archivos.py`) that accepts A's consistent backup manifest/snapshot and verifies every referenced final key's size/SHA, reports missing/inconsistent/unreferenced objects, and exports bytes to an operator-held private backup. An optional export writes only the selected local destination; it does not mutate the source database/store. Reuse already verified immutable local copies for incremental backups, with integrity checks, to avoid consuming the free egress allowance repeatedly. Never claim Supabase DB backups include file bytes.

Provide A the exact manifest/tool contract early. Demonstrate one synthetic restore against disposable Postgres plus an isolated target store, including geometry/history references, one missing/corrupt object and a pending version without staging. The verifier reports orphans and never sweeps them. A owns operational session/lease reset and the final operator runbook. No dependency on paid PITR, provider object versioning, lifecycle rules or backup automation.

## Verification and handback

Use accepted backend conformance tests plus focused lifecycle faults. Run service changes against SQLite and disposable Postgres. Use local provider tooling if already practical; deterministic SDK/HTTP fakes are acceptable for local development but explicitly leave real-provider collision/atomicity, full-size reliability and quota behavior for the hosted gate. Supabase recommends resumable uploads above 6 MB, so 20/25 MiB whole-file success on the actual host is a required proof, not an assumption.

Run normal repository checks before each push and obtain CI on the final head. Reuse existing parser/renderer evidence; no broad browser, 25k-record or heap-slope exercise. A owns the combined application/browser journey.

Hand back early slice SHA first, then final PR/base/code/head SHA, exact-head CI, official SDK pins, public interface/manifest definitions, focused results and remaining real-provider gates. Do not claim deployed acceptance. A may integrate your exact early commits while you finish; do not rewrite history or write A's branch.

Authorized: local implementation, isolated dependencies, synthetic tests, new branch pushes and draft PR. Stop before resource provisioning, payment methods/billing, account/secret changes, deployment, real data or GitHub PR/main merge. Keep working on independent tasks if cloud access is unavailable. A is a different Claude session/computer/account; the owner relays handbacks and fetchable commits.

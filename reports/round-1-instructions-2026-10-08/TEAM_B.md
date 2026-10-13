# Team B — packet 1B: attachment lifecycle core

Read START_HERE.md and ATTACHMENT_CONTRACT.md at this instruction commit. They are the implementation contract; do not follow older unresolved/proposed labels where this packet resolves them.

## Start and scope

First finish and hand back your already assigned memory-budget investigation on its existing separate branch: final report, exact measured implementation/head, limitations, checks and draft PR. Do not interrupt it or quietly merge its prototype into the application. Once that handback is submitted, you may begin **1B without waiting for its supervisory review**: memory/display strategy is not a dependency of attachment lifecycle. Preserve the research branch for possible later corrections.

Use the exact baseline/branch protocol in START_HERE.md. Your new branch is `claude/team-b/attachment-lifecycle`; your new report is `reports/team-b-attachment-lifecycle-2026-10-08/START_HERE.md`. Depend on accepted P1/P2, parser and storage. You do not need Team A's new create/list API: seed fictional terrains/bases through test fixtures, then use real sessions and P2 authorization for domain operations.

This packet authorizes the actual local/fake lifecycle repository and service, not another general design investigation. Implement all operations, invariants and starting policies in ATTACHMENT_CONTRACT.md, with no HTTP registration, UI, cloud provider, schema/auth rewrite or renderer changes. If an accepted prerequisite cannot support a concrete required case, provide the smallest reproducer and exact A-owned change request; continue independent cases.

## Implementation boundaries

Own new `server/repo/archivos.py`, `server/archivos.py`, dedicated `tests/test_archivos*.py`, fictional `tests/fixtures/archivos/` and your report. Refine naming only within these owned modules; keep the reserved summary hook. No edits to `server/app.py`, `server/auth.py`, `server/db.py`, `server/postgres.py`, terrain/base modules, shared test fixtures, CI/deployment or application UI. Do not modify accepted parser/storage behavior incidentally.

Use the actual `AlmacenLocal` and `AlmacenEnMemoria` protocol and actual `procesar_kmz` output. Keep slow work outside write transactions. Test the P1 mutual attempt/geometry constraints at commit. No invented in-memory database substitute for the SQLite/Postgres lifecycle tests, no authorization stub passing as acceptance, no durable/background job infrastructure.

## Acceptance matrix

Run the shared behavior cases on SQLite and a disposable UTF-8 Postgres database. Controlled barriers and a test clock must make races deterministic; use distinct connections. Record which guarantee comes from the existing advisory lock and do not call that a row-lock-only result.

1. **Happy paths:** blank fixture terrain; PDF start/stage/complete/read metadata; single-candidate usable KMZ activation; ambiguous KMZ explicit selection; holes/multipart real parser fixtures; explicit retained-version activation. Correct audit actors/current base; stable terrain version/update stamps throughout.
2. **Inputs and boundaries:** exact/over PDF and KMZ byte limits, declared/actual size and hash mismatch, wrong magic, malformed/rejected KMZ, empty/unsafe display filenames, parser-budget rejection, missing staging/final object, storage exceptions and oversized streamed chunks. Preserve last valid layout. Reuse parser/store fixtures; do not duplicate their whole test suites in this packet.
3. **Identity and permissions:** initiator-only completion, admin/initiator cancellation, arbitrary/other-user IDs, no-scope/missing indistinguishability, archived terrain/base and all file/history/summary authorization. Secrets/keys/session reference absent from serialized results/audit. No access through guessed idempotency keys.
4. **Idempotency and decisions:** start replay/changed body/different actor; completion during live lease then terminal replay; explicit retry/selection same key versus competing key; two replacements from one revision; late completion after newer activation; cancelled/retired uploads never resurrect; stale explicit choices conflict without partial decisions.
5. **Lease and failure recovery:** crash after copy, after parsing and before commit; expired lease takeover; old holder returns late; completion deadline versus valid lease; storage failure followed by full retry; uncertain-commit cleanup never deletes a referenced final. No successful terminal state lacks its stored outcome. Read-only expiry writes nothing. Cap counts effective pending uploads across bases safely.
6. **Scope races, both orders:** grant revocation, terrain transfer, terrain/base archival, account deactivation/role change, logout, credential reset and session expiry between start/slow work/final transaction. Losing authority causes no terminal version/attempt/decision/event write. If attachment locks first, administrative mutation waits or rolls back cleanly. Use P2's real helpers and fixtures; no dependency on A's unfinished transfer route.
7. **Cross-row invariants:** another terrain/attachment/version/attempt geometry cannot activate; `listo` attempt and geometry commit together in the required order; non-usable geometry never activates; terminal rows/history immutable; no deletion of finalized versions; retirement removes the active descriptor but retains history; transfer does not duplicate files.
8. **Concurrent files and cells:** attachment operations do not bump terrain version or overwrite cell data. Concurrent decisions have one valid serial outcome and exact audit effects. Prove summaries replace correctly when a lower-revision PDF changes and another attachment has a higher revision; no `revision_max` shortcut.
9. **Transaction duration:** instrument a test storage/parser barrier to prove the DB write boundary is released during slow work. Assert the final recheck happens after that barrier. Report measured timings and memory for representative bounded files without claiming hosted performance.

For read/replay authorization after transfer, do not rely on a previously cached success or start-time role. For cleanup failures retain recoverable operational state and report it; do not conceal failed removal as successful garbage collection. A permission-denied request must not mutate inaccessible records just to perform lazy expiry.

Run `./verificar.sh` or its disclosed components, Python 3.9, applicable ruff/mypy and full GitHub Python/disposable-Postgres and JS checks at the handback head. Include critical negative controls or regression evidence for races, idempotency and uncertain-commit cleanup. Do not add long sleep-based timing tests where barriers suffice.

## Handback

Open a separate stacked draft PR targeting the frozen integration baseline, with exact instruction/main/baseline/head SHAs and no unrelated changes. Provide:

- the lifecycle/state/operation matrix and final public service signatures;
- fictional request-like inputs and safe result/error examples for later handlers;
- exact permissions, lease/replay/deadline behavior and cleanup limitations;
- parity/race results for both databases, local/fake storage results and measured bounded-file evidence;
- explicit requests reserved for A route registration and later 2B transport, without modifying A files;
- any unresolved issue, test skip or unsupported hosted assumption.

Stop for supervisory review. 2B attachment HTTP handlers and 3B file widgets are not released yet. No merge, deployment, provisioning, real account/data operation or new autonomous check-in is assigned.

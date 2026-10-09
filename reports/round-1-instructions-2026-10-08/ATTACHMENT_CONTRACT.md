# Attachment contract for Round 1

This is the supervisory consolidation for the local/fake lifecycle implementation, based on accepted P1/P2 and PR #12 at `28bf0dbbf718571e35d501a7810d7e7d882ee3dd`. It supersedes conflicting sketches and outdated statuses in that report. The owner requested execution of the first pair; the following starting defaults are selected for this packet. Cloud provisioning, hosted limits, a provider and the production display budget are not decided by it.

## 1. Sources and precedence

Use the exact heads in START_HERE.md. Within the historical attachment proposal, §9 replaces older conflicting lifecycle text. This document then overrides §9 where specified; actual accepted schema-10 constraints and the P2 transaction interface govern the implementation. Do not weaken a database constraint to make an old sketch work.

Read P1's five stricter writer requirements and corrected NULL-check/backup notes at `edf9bcd1dc51e74a627d54d5ce01d37113206055`, `reports/team-a-attachment-schema-2026-10-08/START_HERE.md`. Read corrected P2 §4 and its appended correction at `5d0844cfd678c2f7ec55ddb4b364275482d1a801`, `reports/team-a-roles-and-bases-2026-10-08/START_HERE.md`. Read B-3S's actual `Almacen` protocol; the old proposal's storage sketch is not authoritative.

## 2. Starting policies

| Decision | Rule for this packet |
|---|---|
| D1 provider | Deferred. Use existing local/fake storage only; no provider SDK or hosted upload claim. |
| D2 size | PDF at most **25 MiB**; KMZ at most **20 MiB**. Enforce declared and actual byte sizes; do not raise global HTTP body limits. Existing parser limits also apply. |
| D3 initial selection | Uploading a KMZ with exactly one valid usable candidate is the explicit choice: its successful completion may activate using the start revision. Multiple candidates require explicit selection. No activation of unusable geometry; preserve old active geometry on failure or pending selection. |
| D4 future batch policy | Per-ID authorized results plus an indistinguishable `no_disponibles` list for missing/out-of-scope IDs. No geometry HTTP transport in 1B; byte/chunk limits will be finalized in 2B against full-limit bodies. |
| D5 deadlines | Upload authorization expires **15 minutes after start**; completion may start until **60 minutes after start**, not 60 minutes after upload expiry. Future read grants last **60 seconds**. Only the initiating account may complete; an initiator or currently authorized admin may cancel. Authorization is rechecked, not inherited from initial upload permission. |
| Pending limit | At most **5 effectively pending uploads per initiating user**, counted across bases without leaking those bases. Account for expired entries without mutating unauthorized terrain rows. |
| History | Default **50**, maximum **100** entries, stable cursor; no unbounded attempt/candidate/file history response. |
| Worker lease | **180 seconds**, per version. Takeover only after expiry. Lease guards and final scope checks are mandatory. No infrastructure worker/queue is added. |
| Retired attachment | Cannot be restored or resurrected in this release. New upload creates a new attachment. Retirement is not deletion: bytes, history and geometry IDs remain available to appropriately authorized history/future snapshots. Terrain archival/restoration is a separate reversible operation. |

Use UTC and a testable clock. A deadline at equality is expired. A lease acquired strictly before the completion deadline may finish afterwards if its own lease is still valid. Completion retries cannot acquire a new lease after the completion deadline. A read-grant TTL is a future upper bound for already-issued credentials, not a promise of instantaneous recall; no credentials are implemented in 1B.

## 3. Identity, permissions and transaction boundary

Files reference the stable terrain UUID. One live KMZ attachment per terrain; replacements are versions of it. PDFs may be separate attachments. Attachment operations never bump `inventory_terrain.version`, its update stamps or `inventory_event` and never overwrite a cell edit.

Use `archivos.ver`, `archivos.subir`, `archivos.retirar`. Resolve every file/version/geometry to its actual terrain; a caller-supplied terrain ID is not evidence of ownership. No session: 401; action denied: 403; missing or out-of-scope resource: the same 404. Use P2's action-specific archived policy; normal new upload/decision writes on an archived terrain are refused. Do not create a parallel role/grant checker.

At the eventual HTTP boundary, `auth.require_terreno` checks the real session at request start. In 1B direct domain tests obtain that same `auth.Sesion` through real fictional account/session setup. Perform a preliminary scoped read before slow work, then **every state-writing transaction** enters `with db.escritura() as conn:` and calls `auth.reverificar_terreno(conn, sesion, terreno_id, capacidad)` before its first attachment mutation. Lock attachment and version rows after P2's account/session/terrain/base/grant ordering. Use the fresh `Alcance.actor` and `base_id` for audit. Do not serialize/log/store `Sesion.referencia`.

The helper's SQLite guard is not a Postgres transaction certificate. On both databases only `db.escritura()` is supported. Keep the existing advisory lock. Attachment-only writes do not request an exclusive terrain lock. No storage copy/read/write/parser operation runs while the database transaction is open. No automatic retry on lock timeout/deadlock: return/propagate the controlled busy result; a caller may repeat the whole operation. This explicitly overrides §9.1's retry-once suggestion.

Both race orders must be safe: if revocation/transfer/archive/account change commits first, deny; if the attachment boundary wins, scope-changing writes wait or fail cleanly. After scope loss, no finalization, attempt, event, stored response or activation may be committed on behalf of the old scope. An already committed lease can remain until expiry; that is operational state, not successful finalization.

## 4. Lifecycle and immutable outcomes

Implement the proposal's operations: start, stage content, complete, cancel, process retry, explicit candidate/retained-version activation, retire, read-only list/history/summaries. Keep upload states, parser results and active layout decisions separate.

**Start:** reauthorize, enforce type/name/size/hash, pending cap, current attachment revision and one-live-KMZ invariant. Insert attachment if new, pending version and event atomically. Client filenames are display-only text, never paths; cap at 255 characters. Keys are server-generated under the accepted store grammar. An existing filename does not overwrite another PDF. Upload start itself is not an active-layout decision.

**Staging:** check initiator, session/scope, pending state and upload deadline before accepting bytes; stream into bounded staging outside a DB transaction. Recheck state before reporting success. A race may leave unreferenced staging bytes, never a terminal pointer or unauthorized attachment mutation. Do not let a late completion make a still-live staging grant capable of altering final bytes.

**Complete:**

1. Authorize the current resource even on replay. In a short transaction, take the per-version lease only for a pending version still within its completion-start deadline; a live competing lease returns `409 procesamiento_en_curso` with retry advice.
2. Outside the transaction, copy staging to a fresh, exclusive final nonce key. Verify **that final object**, streamed, for actual size, declared SHA-256 and PDF/KMZ signature. The accepted bounded KMZ parser runs on those verified bytes, not staging.
3. In a new short write transaction, reauthorize, lock current attachment/version and verify your lease ID, live lease and pending state. Atomically write the terminal version/outcome, completion attempt and its geometry where applicable, conditional pointer decision and audit; remove the owned lease. The P1 rule is **insert a `listo` attempt with its chosen geometry UUID first, then that geometry in the same transaction**. Commit-time deferred constraints must succeed; never insert one without the other.
4. An initial usable single-candidate KMZ may activate only if `archivo.revision == revision_base`; PDF completion uses the same compare-and-set. KMZ current-version and geometry pointers change together. Failed/stale replacement leaves the previous layout intact. Store a superseded verified version and parser result as history, with `aplicada = 0` and the allowed reason. A no-selection/unusable parser result may be a valid available file without an active layout; do not label it a transport failure.
5. Cancellation/retirement that won first leaves the pending version cancelled; late work cannot rewrite it. A lost/expired lease cannot finalize even if the bytes are valid. Delete only your conclusively unreferenced output; otherwise leave it for future safe cleanup.

`disponible` and `fallido` terminal rows must contain their committed completion outcome from the same transaction. No interval exists with an available version but no completion outcome. P1's final/terminal timestamps, nullable actor rules and outcome/check constraints all apply. Verification failure is `fallido`; storage outage is retryable without a false terminal outcome; parser failure/rejection and transport verification failure remain distinguishable. Release an owned lease on handled failure only through an authorized guarded write; otherwise allow expiry.

**Replays:** completion terminal replay returns the original stored completion attempt and `aplicada`/`motivo_no_aplicada`, plus explicitly current attachment state. It must not rerun the parser or rewrite terminal rows. Cancelled/expired uploads return their defined conflict. Explicit reprocessing/selection uses a scoped idempotency key and the same lease mechanism; a different concurrent key receives the in-progress conflict. Every active decision uses `expected_revision`; no stale decision resurrects retired content or overwrites a newer selection.

Idempotency keys are scoped by actor, operation and resource, with a normalized payload hash. Identical replay is stable, changed payload conflicts, and another user cannot recover private cached results by guessing a key. Reauthorize the current resource on every replay before returning anything. Existing `inventory_operation_result` can be reused without exposing its raw stored body indiscriminately.

## 5. Preservation, read behavior and cleanup

- Activation requires an available version and a `listo`, usable geometry belonging to that **same version, attachment and terrain**. Cross-version substitution is refused even within the same attachment. Geometry IDs and final bytes remain immutable for future snapshot references.
- Reads do not mutate expiry or acquire a fake actor. Project an overdue pending upload as expired only when there is no live lease. Persist lazy expiry only in an authorized write transaction, preserving audit semantics. Automatic retirement of an empty attachment must not retire one with usable content or another live upload/lease.
- Read summaries are bounded and caller-aware: counts and at most five recent PDFs, live KMZ state, own pending details and safe generic status for another caller's in-progress upload. No `revision_max` aggregate token. Returning a changed summary does not touch terrain versions.
- Public catalog DTOs never contain attachment/geometry internals, comments or keys. Private DTOs never contain storage keys, credentials or session references. Geometry bodies are separate from record summaries.
- Cancellation/retirement retains all finalized history and bytes. Scope follows the terrain's current base. Frozen snapshot references will later use exact version/geometry IDs, not the mutable current pointer.
- A DB commit exception can be ambiguous. Do **not** delete a final object merely because the client observed an exception: establish that it is unreferenced using a fresh successful DB check, or leave it for safe cleanup. Protect live leases and all referenced terminal objects. Two completions may only clean their own losing nonce, not another operation's output.
- No scheduled/destructive orphan sweep or cloud cleanup is added in 1B. Report unreferenced bytes and define safe future sweep predicates. Test best-effort local cleanup and crash/takeover behavior. Restore/backup tests must preserve durable rows and exclude operational leases, as P1 already specifies.

## 6. Interface ownership and later packets

B adds `server/repo/archivos.py` for SQL and `server/archivos.py` for orchestration, with dedicated `tests/test_archivos*.py` and fictional fixtures under `tests/fixtures/archivos/`. A must not create duplicate attachment modules. Keep the accepted `server/almacen.py` and `server/kmz.py` interfaces stable; any needed repair requires a separate finding, not an incidental rewrite.

B's report freezes the public domain-operation signatures and safe result/error shapes for 2B. At minimum cover iniciar, escribir contenido temporal, completar, cancelar, reprocesar, activar, retirar, listado/historial and scoped summaries. No request object or HTTP response implementation is required in the service; accept the validated internal session reference plus explicit parameters and injected storage/clock as needed. SQL stays in `server/repo/`.

Reserve `resumenes_de_archivos(conn, inventory_ids, sesion)` as the later page-batch summary hook. It must scope/authorize the IDs and pending details even when a caller gives IDs from several bases; do not assume merely accepting a session parameter checks it. The exact Python return DTO and helper details are part of B's report before A mounts it in 3A. A's 1A does not import unfinished B services. No HTTP route, cloud grant, frontend component, map worker or terrain DTO mounting is part of 1B.

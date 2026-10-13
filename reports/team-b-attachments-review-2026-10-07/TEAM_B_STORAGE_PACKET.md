# Team B — B-3S: standalone local/fake storage core

## Assignment and baseline

Implement the independently testable **byte-storage core only**, split out of PR #12's proposed B-3a. This is not authorization for the attachment repository/state machine or HTTP handlers. No Team A code or cloud decision is needed for this packet.

Repository: [Andre07-hash/ARA-MAP](https://github.com/Andre07-hash/ARA-MAP). Fetch current main (at issue `09452fd26d38319567dce28a89db100ea61c739a`), report any change, and start `claude/team-b/storage-core`. Read this instruction commit with `git show`; do not develop on the supervisor's branch. Preserve PRs #9, #11 and #12; do not merge them to get instructions.

Read [REVIEW.md](REVIEW.md) and PR #12's report at `ba3ad38599bb5f968164424f2ef6244e9ee24aca`, especially §2.4 and §5.1. This packet supersedes the proposed requirement to wait for P1 **only for this extracted storage core**. The rest of B-3 still needs the shared contract, P1 and P2.

## Owned files and interface

Own `server/almacen.py` (with narrowly scoped B-owned helper modules only if justified), dedicated `tests/test_almacen*.py`, fictional fixtures and a report under `reports/team-b-storage-core-2026-10-07/`. Use Python 3.9 and the standard library; no new dependency, frontend change, app wiring, schema/auth/repository/route/CI/deployment edit.

Provide local filesystem storage plus an in-memory fake behind the same byte-operation interface. Constructors receive an explicit root/configuration. Importing or constructing a backend must not select production paths, create credentials or start a server. Tests use temporary roots; no writes to the project's real `datos/`.

Retain the proposal's operation vocabulary where applicable:

- `guardar_temporal(clave, bloques, limite)`: an internal byte-stream operation for a future authorized caller. Accept only a staging key, enforce a required caller-supplied positive byte limit and bounded chunks, and allow a complete replacement of staging. It is not an upload URL or HTTP endpoint.
- `copiar(origen, destino)`: copy a staging object to a unique final key. Add an explicit byte-limit parameter if needed to keep the operation bounded. A pre-existing destination must never be overwritten, including under concurrent calls. The caller selects a fresh opaque nonce key for each completion attempt.
- `leer(clave, limite)`: bounded streaming bytes; an oversized object raises a distinct limit error rather than silently returning truncated success. Readers must close resources promptly on early termination or failure.
- `tamano_de(clave)`: byte count or the documented absent result.
- `borrar(clave)`: only an exact validated key; no recursive prefix deletion. Document idempotent missing-key behavior. A future higher layer is responsible for proving that a final key is an unreferenced candidate before deletion. This core cannot decide database reachability.
- `listar(prefijo)`: a lazy, bounded-memory iterator over metadata, with explicit allowed prefixes. It does not trigger expiry or cleanup.

Freeze the exact signatures, metadata/error types and fake-backend behavior in the PR report so the later repository packet can use them. Do not implement `emitir_subida`/`emitir_lectura`, signing, URLs, sessions, role checks, object-hosting endpoints, PDF interpretation or KMZ parsing here. Cloud support remains a later adapter. The interface may reserve those higher-layer capabilities in documentation only.

## Required invariants

1. **Keys and containment:** keys are server-generated opaque identifiers under `temporal/` or `final/`; original filenames never become paths. Reject absolute paths, traversal, invalid namespace/key forms and symlink escapes. Keep reads, writes, copies, deletes and listing inside the injected root. Report the local trust model and avoid an unsafe check-then-open shortcut.
2. **Atomic staging:** a successful write exposes the complete staging object. A failed, interrupted or oversized replacement must not leave truncated content appearing successful or destroy an existing complete object. Concurrent staging replacement and copy must yield a complete snapshot or a clean failure, not mixed bytes. Clean up owned partial files.
3. **Final immutability:** finalize into a fresh key atomically without overwriting any existing final object. Once a copy succeeds, later staging writes do not change that final object's bytes. Two competing copies to one final key must produce one winner and an explicit collision, with the winner unchanged. Two different nonce destinations may both succeed; the later database CAS chooses which one to reference.
4. **Verify after copy:** the caller can independently stream the final object to compute byte count and SHA-256. Do not cache/reuse a staging hash as proof of final content. Application-level hash/type validation and active-pointer decisions remain out of scope.
5. **Bounded operation and explicit failures:** limits are arguments, not decisions about PDF/KMZ product caps. Stream large objects instead of buffering complete files in the local adapter. Distinguish absent, invalid key, collision, limit and storage failure sufficiently for the future service layer; no credentials or arbitrary filesystem paths in user-facing error text.
6. **Equivalent fake:** it obeys the same observable semantics and supports deterministic failure injection for copy/read/write/missing-object scenarios. Fault controls stay in the fake/test surface; no production bypass flag. An in-memory fake naturally holds fictional bytes in memory and must still enforce the same limits.

No automatic garbage collector, scheduled job, command-line cleanup, production root default or global body-limit change is included. Do not invent database tables or mock Team A's schema inside production code to make this task appear integrated.

## Evidence and handback

Run the same behavioral tests against local and fake backends where applicable. Include empty content, exact limit/one byte over, arbitrary binary bytes, staging replacement, failed replacement preserving prior content, copy/read faults, immutable final bytes after staging overwrite, simultaneous copies to the same destination, early reader close, path/symlink escape attempts and safe exact-key deletion. Use bounded large synthetic streams to demonstrate the local adapter is streaming; report measurements without claiming cloud capacity.

Run `./verificar.sh` and the applicable existing lint/type checks. If the environment has no zsh, run and accurately report its components. Obtain green GitHub CI; use disposable resources only. Postgres has no new feature-specific role in this storage-only PR, and no database is needed for its tests.

In parallel, update PR #12's documentation to address the four contract refinements in REVIEW.md; keep those commits on its existing documentation branch, not in the storage PR. Do not wait for A to write those clarifications.

Return the separate storage draft PR, instruction/baseline/head SHAs, exact interface, test evidence and limitations. Return PR #12's revised head separately. Stop for supervisory review; the attachment repository, state machine, handlers and cloud integration still need their own release packet. Do not merge, deploy or provision services.

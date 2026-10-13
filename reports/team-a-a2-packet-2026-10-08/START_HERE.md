# Team A — A-2/P2 roles, work-base access and transaction-scoped authorization

## Start implementation now

P1 is accepted at **`edf9bcd1dc51e74a627d54d5ce01d37113206055`**, PR #15. Build A-2/P2 on a new branch **`claude/team-a/roles-and-bases`** from that exact commit. This is an explicitly authorized stacked draft; target `claude/team-a/attachment-schema` while P1 remains unmerged. Keep PRs #14 and #15 unchanged. If the dependency has landed on main, use its actual descendant and report the ancestry. Re-fetch main and dependencies; do not silently move to an unreviewed head.

Repository: [Andre07-hash/ARA-MAP](https://github.com/Andre07-hash/ARA-MAP). Read the supplied instruction SHA with `git show`; do not develop on the supervisor branch. No new owner decision, provider choice or B display handback is required to begin.

This implements the backend A-2 scope from Team A's preparation, plus P2's atomic recheck. It does **not** implement the grid, attachment handlers, transfers, custom-column editing or the complete A-3 record workflow. The application is not ready for an employee rollout merely because these backend permissions pass.

Required references:

- Owner-approved `reports/workspace-contract-2026-10-07/SHARED_CONTRACT.md` at `3bada9fa4e9e2eee517f453846aa4af037ddd7fa`.
- Your preparation report `reports/team-a-master-table-prep-2026-10-07/REPORT.md`, §§2.6 and 3, at `5e1b1bfc0f8a2a663972ca45f77128b1c1729cd6`; the approved shared contract overrides its older proposals.
- B proposal `reports/team-b-attachments-contract-2026-10-07/REPORT.md`, §9.1, at `28bf0dbbf718571e35d501a7810d7e7d882ee3dd`, as refined by the transaction requirements below. Its claim that existing admin operations require no new synchronization work is not assumed: those writers do not all exist yet.
- P1 acceptance and writer rules in `reports/team-a-p1-review-2026-10-08/ACCEPTANCE.md` and `START_HERE.md` in this instruction history.

## Owned implementation

Use A-owned `server/auth.py`, `server/app.py`, session/inventory API modules, new narrowly scoped work-base API/repository modules, `scripts/cuentas.py`, and dedicated tests. New SQL belongs in the repository layer where practical; do not reorganize unrelated existing auth code just to move SQL. Small shared transaction/request/protocol changes are allowed when needed for the secure interface below and must be documented. Use schema 10 as it stands; no new schema version is planned. Raise a concrete schema incompatibility before introducing a migration.

No B-owned parser, renderer, storage or future file repository/handler edits. No frontend, CI, deployment configuration, new framework/dependency, real account operation or production migration. Tests and local demonstrations use disposable databases and fictional users.

## 1. Role policy and complete route coverage

Implement the approved capability sets:

- Both roles: `maestra.ver`, `maestra.editar`, `maestra.archivar`, `columnas.gestionar`, `archivos.ver`, `archivos.subir`, `archivos.retirar`.
- Admin only: `maestra.global`, `bases.gestionar`, `derivados.ver`, `derivados.gestionar`, `usuarios.gestionar`.

Capabilities grant actions; operators additionally need a current base grant. No per-user capability switches. Unassigned terrains remain admin-only.

The dispatcher must enforce a declared capability for every registered private route, before its handler executes, with default denial for any unmapped private route. Preserve the exact existing anonymous allowlist, login throttling, cookies and unknown-API behavior. Legacy imported bases/maps/folders/formats/import/export are admin-only through `derivados.*`, including any nominally read-only POST such as export. Audit the actual route registry rather than hard-coding its old count.

The existing **unscoped** inventory listing and creation routes become admin-only (`maestra.global`); do not let an operator use their query/body to reach the aggregate. The new base-scoped record list/create routes are A-3, not this packet. Existing terrain detail/history use `maestra.ver` and PATCH uses `maestra.editar`, with current terrain scope checked server-side. Operators can use these direct record routes only on records assigned to their accessible active bases. Do not expose internal/custom/attachment fields simply because their columns now exist.

401 means missing/expired/revoked session or inactive account; 403 means missing action capability; 404 must be indistinguishable for unknown versus out-of-scope resources. Keep the existing `ApiError` response envelope and put machine-readable codes in its established detail object rather than inventing a second transport format.

## 2. Work-base and grant endpoints

Implement the preparation's following routes only:

| Route | Behavior |
|---|---|
| `GET /api/maestra/bases` | Admin sees work bases; operator sees only granted, active work bases. Filtering/counts happen inside the authorized database scope. Active only by default; admins can request archived bases explicitly. |
| `POST /api/maestra/bases` | Admin creates an empty work base. A nonblank display name is required; terrain business fields and files are not. |
| `PATCH /api/maestra/bases/:bid` | Admin renames an existing base using `expected_version`. |
| `POST /api/maestra/bases/:bid/archivar` and `/restaurar` | Admin reversibly changes base archive state using `expected_version`. Preserve every terrain, revision, column, file and grant. This operation changes work-base access, not public terrain visibility. |
| `GET /api/maestra/bases/:bid/acceso` | Admin reads current grants. No operator enumeration of other accounts. |
| `PUT /api/maestra/bases/:bid/acceso` | Admin atomically replaces the explicitly supplied set of operator IDs using `expected_version`; validate the complete request before changing anything. No implicit wildcard/all-users grant. |

Define and document exact request/response examples in your handback. Use UUIDs, existing version/error conventions and actor identity from the session. A changed base/grant set increments the base's version and records its base event; additions/revocations also append `team_user_event` records so removed grants remain auditable. Stale submissions return 409 and make no partial change. Reject invalid/nonexistent targets as a whole. Granting an inactive account should be rejected; removing an inactive account's grant remains possible. Duplicate IDs in the input may be normalized as a set, but do not create duplicate grants/events. No new name-uniqueness rule is required.

Operators cannot read or reopen an archived base. Admins may inspect, manage grants, and restore it. Normal terrain/file writes against an archived base are read-only until restoration, even for an admin; return a distinct documented 409 after authorization. Archiving a work base must not rewrite terrain publication state, exported/saved maps, attachment pointers, or terrain cell versions. No transfer, permanent delete or terrain archive/restore endpoint is added here.

## 3. Sessions, CLI bootstrap and audit

Extend session responses with the authenticated user's role, capability list and permitted base scope, using the prepared `capacidades`/`alcance` vocabulary. Anonymous responses stay anonymous. These fields help later navigation; the server remains authoritative. Never serialize a session token/hash, password hash, credential revision secret, or internal session reference. Scope reflects current grants on every request; no stale per-process authority cache.

Extend the existing explicit-target `scripts/cuentas.py` with role selection on creation (default operator), a role-change command, and role information in listing. An actual role change increments `credential_revision` and invalidates old sessions. Preserve reset/deactivation revocation. Add append-only account/role audit for these command actions in the same transaction; CLI events use the accepted nullable actor ID and an explicit CLI actor label, not an invented logged-in user. Keep passwords out of command arguments and output. Do not auto-promote an account or infer an administrator from the first row.

No new account-management HTTP routes or UI in this packet. Release notes must provide an explicit-target administrator bootstrap, sign-in verification and recovery procedure for a future authorized operator. Apply the reviewed schema prerequisites before the role command and verify readiness; do not silently migrate a cloud target from that command. Existing installations receive operator/no-grant defaults: enforcement must not be deployed before administrator bootstrap. Demonstrate the procedure with disposable fictional accounts only. CLI administration remains a trusted, explicit-target operations action with its own audit identity; do not fabricate a web session for it or expose that trusted path to HTTP callers. Update misleading module/CLI descriptions that currently say all users always have equal powers.

## 4. P2 interface for B and the transaction boundary

Provide the agreed A-owned entry points:

- `auth.require_base(request, base_id, capacidad)`
- `auth.require_terreno(request, terreno_id, capacidad)`
- `auth.reverificar_terreno(conn, sesion, terreno_id, capacidad)` for an already opened write transaction.

Use a typed internal scope result (`Alcance` or equivalent) that exposes a trusted actor, current terrain/base identity and a **revalidatable session reference** for B. Freeze its exact fields/types and a short usage example in the handback. The reference must identify the original authenticated session and credential generation, not just a user ID or cached role. Derive it from real server-side session validation of the cookie; never trust body fields or a fabricated `request.user` dictionary as authentication. The reference is internal and must not enter JSON, logs, audit payloads or idempotent response storage.

The write-boundary helper re-reads the session (expiry/revocation/credential revision), active account, current role/capability, terrain membership/archive state, current base state and current grant **using the same connection/transaction that performs the mutation**. Resolve a terrain's current base from the database, not a previously supplied base ID. Authorized reads may inspect archived terrains in an accessible active base; ordinary edit/upload/retirement capabilities reject an archived terrain with 409. Do not let an out-of-scope caller learn archive state before its 404. Later restore/transfer operations will have their own explicit policy.

Provide an A-owned, documented transaction entry mechanism that B can actually use. B must not guess how to open a safe SQLite transaction. Requirements:

1. **SQLite:** acquire the write reservation before the authorization reads (normally `BEGIN IMMEDIATE` at the outer boundary). Existing `db.transaction()` uses SAVEPOINT and is not by itself proof of an immediate write transaction. Do not try to upgrade an already-read transaction silently; either enter through the correct outer boundary or fail safely. Preserve existing callers and rollback/close reliably if a deferred FK fails on commit/release.
2. **Postgres:** keep the existing session transaction/advisory-lock behavior. Within that boundary use locking reads sufficient to serialize authorization dependencies against role/reset/deactivation/logout, base archival, grant revocation and future terrain transfers. §9.1's `FOR SHARE` scheme is acceptable if implemented correctly. Document one consistent row-lock order and any ordered multi-user/multi-base acquisition needed by admin writers; user → session → terrain → base → grant precedes B's attachment/version locks. Do not remove the advisory lock as an incidental performance change.
3. **Both orders matter:** a scope change that commits before the final recheck denies the attachment write; a scope change that races after the write boundary is acquired must wait or cause a clean rollback, never produce an unauthorized commit. Admin mutations must participate in that synchronization.
4. **No long work under locks:** copy/read/verification/parser work happens outside the database transaction. Authorization is checked before starting and checked afresh after that work. Do not run storage I/O merely to test the helper; deterministic test barriers and fictional attempted writes suffice.
5. **No hidden retry side effects:** lock errors/deadlocks/timeouts must leave no partial mutation or audit. Document bounded retry/error behavior; any retry restarts authorization and the entire short transaction, not external I/O or an isolated UPDATE.

Existing A-2 mutations also use the proper final authorization boundary, including base/grant administration. For current terrain PATCH, preserve `base_id`, `tipo_terreno` and `custom_json` when writing a new revision; no endpoint may reset these fields merely because A-3 has not exposed editing them. This small preservation dependency is pulled forward from A-3 because A-2 authorizes edits of assigned records. Do not add type/custom editing, transfer logic, price-rule changes or public exposure of those fields.

Grant, role and base reads used for scope lists must be filtered in SQL. Global inventory performance/pagination remains a later packet; do not claim that this changes the existing admin aggregate into the final scalable master table.

## 5. Acceptance evidence

Use the same behavioral matrix on SQLite and disposable Postgres where applicable, with actual sessions, two admins, operators with zero/one/multiple grants, two active bases, an archived base, and assigned/unassigned/archived terrains.

- Admin creates an empty base, grants it, renames/archives/restores it, and revokes access, with conflict protection and exact audit/version effects. Rejected mixed grant lists have zero partial changes. Archived bases preserve all dependent content and public output.
- Operator sees only its granted active bases; cannot use global/legacy/admin routes; can read/edit only an authorized terrain; inaccessible/missing IDs produce equivalent 404s. Unknown and unmapped private routes never become public. Test the real dispatcher and actual route registry, not only a capability dictionary.
- Session role/scope responses match backend rights. Grant revocation takes effect on the next request; role changes/reset/deactivation invalidate old sessions. Forged actor/role/base information in body/request metadata cannot grant access.
- Exercise role and bootstrap CLI commands only against explicit disposable targets; missing target is refused. Defaults stay operator. Verify audit and recovery, without printing credentials.
- PATCH preserves new revision fields, existing conflict behavior and public allowlists. History returns no newly added custom/private fields outside the existing authorized response contract. This packet creates no source-base custom-history projection; the later transfer/custom workflow must implement its redaction before enabling it.
- Race tests use two distinct database connections and controlled barriers: authorization followed by grant revocation, base archive, role change, deactivation, logout, credential reset and fixture-simulated terrain transfer before the final write. Then reverse the lock order and prove the scope-changing writer waits or a clean rollback occurs. Include session expiry before final recheck. A raw fixture transfer is test setup, not a new transfer API.
- Demonstrate the documented B usage pattern around a tiny fictional attachment/audit mutation with a real authenticated session and transaction. Losing scope must leave no mutation/audit. The example is a test only, not a production attachment repository or fake authorization bypass.
- Postgres tests must say whether serialization came from the existing advisory lock or row locks. If testing the additional row-lock guarantee directly, use disposable independent connections without the advisory wrapper; do not claim a row-lock test when the second connection never got past the outer advisory lock.
- Preserve public catalog behavior, cookie protection, login throttling, existing admin workflows, schema/backup checks and Python 3.9 support. Adapt old all-users-equal fixtures explicitly to admin/operator roles rather than weakening expected authorization results.

Run `./verificar.sh`, applicable lint/type checks, and GitHub Python/disposable-Postgres and JavaScript CI at the returned head. Report local skips and separate browser/hosted evidence honestly. No frontend acceptance or production capacity claim is expected. The separate hosted adapter work in PR #4 remains a separate integration prerequisite; do not absorb its deployment configuration or claim this packet resolves that PR.

## Handback and stopping point

Return a separate draft PR with instruction/main/P1/head SHAs; route-to-capability matrix; concrete helper/session-reference/transaction interface and B usage example; new base/grant API examples; race-test results; and administrator release/recovery notes. Put the report under `reports/team-a-roles-and-bases-2026-10-08/` and append later corrections without erasing history. Correct stale PR-body head labels when reporting new heads.

Stop for supervisory review of this implementation. A-3's scoped record creation/listing, transfer/archive workflows and grid remain later assignments; full B-3 is not assigned by this packet. Team B continues its display investigation independently. No merge, deployment or provisioning is authorized; the supervisor coordinates the next attachment lifecycle handoff against your exact tested interface.

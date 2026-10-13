# A-2/P2 supervisory review — two corrections before acceptance

Reviewed [PR #17](https://github.com/Andre07-hash/ARA-MAP/pull/17), exact head **`1e27715afc74cfe342b1c209d2881c4f05ffef02`**, stacked on accepted P1 `edf9bcd1dc51e74a627d54d5ce01d37113206055`. Instruction: `afd4865892972d8ebd39a31bd5b8ec6c72a74d63`, `reports/team-a-a2-packet-2026-10-08/START_HERE.md`. October 8, 2026.

**Disposition:** the implemented role/scope policy and proposed P2 interface fit the packet. Request the targeted F1 code/test correction and F2 release-note correction below before accepting this head as B's integration dependency. The operator UI and administrator bootstrap are known release prerequisites, not reasons to stop development. No new schema, provider choice or real-account action is required for these corrections.

## F1 — [P2] Postgres contention before the handler bypasses the promised 503

`server/app.py:162–164` opens `db.session()` to authenticate the cookie **outside** the error-handling block beginning at line 188. `postgres.session()` can time out taking the workspace advisory lock; it raises the raw Postgres lock exception. The new `db.escritura()` translation and `except db.OcupadoError` at line 199 do not cover this earlier path.

Every authenticated write goes through that path first. If another transaction holds the workspace lock longer than 30 seconds, a request never reaches the new write boundary and gets a dropped connection instead of the documented JSON `503` with `detalle.code = "ocupado"`.

Independent reproduction on disposable **Postgres 17.11**, UTF-8 database, real HTTP server, real fictional administrator session:

1. Set up the PR's `RolesPostgres` fixture.
2. On a separate raw connection, hold the real advisory lock for that fixture's schema.
3. Send an authenticated `POST /api/maestra/bases` using an HTTP timeout longer than the real 30-second lock timeout.
4. Result: **`RemoteDisconnected` after 30.01 seconds**, not an HTTP response. Base count is unchanged.
5. Release the lock and repeat: **200**.

[reproduce_lock_timeout.py](reproduce_lock_timeout.py) runs this diagnostic against a supplied disposable archive and an explicitly supplied `ARA_MAP_TEST_DATABASE_URL`. It creates/deletes a unique fixture schema and uses fictional accounts only. It needs the existing development psycopg dependency. Run from outside production configuration; never point it at a hosted application database. Example: `python reproduce_lock_timeout.py /path/to/disposable/pr17/archive`, with that test variable already set. The current script reports observations; its zero exit status does not mean the expected 503 was returned.

**Required correction:** cover database acquisition/authentication as well as handler work with controlled error handling, and translate actual lock/busy/deadlock/timeout failures at the appropriate shared boundary. Preserve the anonymous allowlist, fail-closed authorization, response envelope and no-retry policy. Do not map unrelated exceptions indiscriminately to "busy". When rejecting before consuming a request body, close the connection consistently. Review the same error path for session/read endpoints and SQLite connection acquisition; do not change SQL policy or remove the advisory lock to avoid this case.

Add a real dispatcher/Postgres contention regression that asserts `503`, `detalle.code = "ocupado"`, no partial mutation/audit, and a successful full-request retry after release. A test-only shorter wait is fine if it exercises the same lock acquisition; also retain coverage for contention inside the final write boundary. Never hold real production locks for a test.

This is an existing dispatcher gap uncovered by the new busy-response contract; the review does not claim A-2 introduced the entire underlying failure path. It nevertheless leaves item 4 of the handback incomplete.

## F2 — [P2] The proposed rollback removes the access policy

The release notes at lines 369–370 say: “Rollback of the code is safe at schema 10: the earlier code ignores roles.” Schema compatibility is not access-policy compatibility. The earlier dispatcher allows every authenticated account into the legacy workspace; reverting to it after operator accounts are enabled restores that broad access. Older record writers also have not been established here as preserving every newer field/workflow.

**Required correction:** remove the blanket safe-rollback claim. Separate administrator recovery (the explicit-target CLI, which keeps role enforcement) from an application rollback. Document that a release cannot revert to code that ignores roles while operator traffic continues. A future rollback needs a reviewed version preserving the access policy, or an explicitly controlled maintenance/access restriction before the switch, plus verification of session behavior and data compatibility. Do not invent an already validated rollback commit. Preserve the original statement as historical evidence with a clearly superseding correction.

No deployment or account changes are requested by this finding. Keep the bootstrap procedure, but state that the role command is run using the reviewed role-aware release code against the explicit migrated target **before traffic switches**, not using the still-running older checkout's CLI.

## Disposition of the seven requested points

| Point | Review |
|---|---|
| 1. Optional `exclusivo=True` | Accept the addition. Writers updating the addressed terrain/base acquire its exclusive row lock directly. Attachment-only writes leave it false unless a later reviewed workflow also updates that row. |
| 2. Refuse an unsafe transaction upgrade | Accept the SQLite guard. Correct the report's universal wording: `en_escritura()` currently accepts non-SQLite connections, including a regular Postgres session; it does not prove every connection came from `db.escritura()`. B must use the documented wrapper on both backends. Do not claim an autocommit Postgres connection is safe or silently broaden B's supported call pattern. |
| 3. Account CLI uses `db.escritura()` | Accept. Account/role mutations participate in the same serialization boundary and audit. No automatic administrator selection. |
| 4. `OcupadoError` and 503, no retry | Direction accepted; F1 must be corrected before the stated HTTP guarantee is accepted. |
| 5. Grant targets must be operators | Accept. Administrators already have global scope. Keep the documented whole-set validation and explicit removal behavior. |
| 6. `maestra.archivar` can reach an archived terrain | Accept as the prerequisite for the later explicit restore workflow. This does not authorize other ordinary edits/uploads on archived content. A-3 must apply its action-specific policy. |
| 7. Legacy fixtures explicitly administrators | Accept. Existing expected results remain intact; the new role matrix supplies operator coverage. |

A future change that removes the workspace advisory lock must revisit synchronization as a separate design change. In particular, grant target-account validation currently relies on that shared boundary; sorting grant rows alone is not a general multi-account locking proof. Nothing in this review authorizes removing the lock.

## P2 interface direction for Team B

The request-start `require_terreno` returns the internal session reference. Slow storage/parser work happens outside the database transaction. Then use **`with db.escritura() as conn`**, call **`auth.reverificar_terreno(conn, sesion, terreno_id, capacidad)` first**, acquire attachment/version locks afterwards, and persist using that fresh scope's actor and base. Let failures roll back the complete short transaction. Do not log/serialize the session reference and do not substitute a caller-provided actor/base. The accepted P1 rule still requires a successful attempt and its geometry to be saved together, attempt first, in the same transaction.

This interface direction is suitable; the exact production integration head remains pending the corrections. It is not the complete B-3 lifecycle/API packet. Team B should continue its already released PR #16 corrections and isolated E1 work, not change plans or edit A-owned code.

## Independent evidence

- Read the changed application files, authorization/transaction helpers, test matrix, handback and route registry at the exact head.
- `./verificar.sh` passed in a disposable archive: **807 Python tests, 96 Postgres-only skips**, full suite on **Python 3.9.6**, and JavaScript. Historical repository symlinks were omitted from archive extraction; application/test source was unchanged.
- `ruff check server/ tests/` passed; `mypy server/` passed (**45 source files**) using the existing development tools.
- Disposable **Postgres 17.11**, UTF-8, Python 3.14: **807 tests passed, zero skips**, including the advisory-lock and independent row-lock matrices. An initial review database was accidentally initialized as SQL_ASCII and produced text/bytes fixture failures; that run was discarded, the database was recreated as UTF-8, and the full suite above passed. The F1 diagnostic also used the corrected UTF-8 database.
- GitHub Python/disposable-Postgres and JavaScript checks are green at the reviewed head, run [37818295221](https://github.com/Andre07-hash/ARA-MAP/actions/runs/37818295221). F1 demonstrates a missing case despite those checks.
- No browser/operator-screen acceptance, hosted deployment or production readiness was tested. No account was selected, promoted or modified outside disposable fixtures.

## Immediate assignment and release decisions

**Team A:** correct F1, F2 and the point-2 documentation mismatch on `claude/team-a/roles-and-bases`, retaining PR #17's stacked target and every accepted dependency. Add focused regressions, run the required checks and return the exact correction/report heads and CI evidence. Append dispositions to the existing report; preserve its original handback. No unrelated refactor, migration, frontend, B-owned code or A-3 implementation in this correction. Stop for re-review.

**Team B:** continue the independent assignment at `75611396a1d085372d5a32cd0c76866d99b3d930`, `reports/team-b-display-review-2026-10-08/{START_HERE,TEAM_B_E1}.md`. These corrections do not require B input.

**Owner decisions for the later release:** name the exact account logins to receive administrator access. The supervisor can recommend a primary administrator and a trusted backup, but cannot choose identities or promote accounts on the owner's behalf without that designation. This decision can be collected before the release; development does not wait for it. The operator-facing grid/navigation must also be accepted before an employee rollout. Naming administrators alone does not make the current operator screen usable. No merge, deployment, provisioning or real-account operation is authorized here.
